"""Frida JS agent injected into the target process.

Injected once via setup(); collect() can be called repeatedly.
sys._debugmallocstats() writes to the C-level stderr (fd 2), so we
redirect fd 2 to a temp file at the OS level for each capture.
"""

from __future__ import annotations

_AGENT_JS = r"""
'use strict';

// _collect: cached callable — set during setup(), invoked during collect().
// Calls _arena_capture() directly via PyObject_CallFunctionObjArgs, avoiding
// PyRun_SimpleString (which compiles a new code object every call) and any
// mutation of builtins (which was implicated in a one-block-per-second leak).
let _collect = null;

// Search all loaded modules for a Python C-API symbol.
// More robust than matching by module name, which varies by platform
// (.so on Linux, .dylib on macOS) and custom build location.
//
// Frida 16+ provides Module.findGlobalExportByName() which scans .dynsym
// directly and works on BOLT-optimised binaries where .gnu.hash is stale.
// Fall back to per-module getExportByName() for older Frida.
function sym(name) {
    if (typeof Module.findGlobalExportByName === 'function') {
        const p = Module.findGlobalExportByName(name);
        return (p && !p.isNull()) ? p : null;
    }
    for (const mod of Process.enumerateModules()) {
        try {
            const p = mod.getExportByName(name);
            if (p !== null && !p.isNull()) return p;
        } catch (e) {}
    }
    return null;
}

function nfn(name, ret, args) {
    const p = sym(name);
    if (!p) throw new Error('symbol not found: ' + name);
    return new NativeFunction(p, ret, args);
}

function makeSetupRunner() {
    const ensure  = nfn('PyGILState_Ensure',  'int',  []);
    const release = nfn('PyGILState_Release', 'void', ['int']);
    const runStr  = nfn('PyRun_SimpleString',  'int',  ['pointer']);
    return function run(code) {
        const state = ensure();
        const ret   = runStr(Memory.allocUtf8String(code));
        release(state);
        return ret;
    };
}

// Returns a function that calls _arena_capture() in the target and returns the
// text.  The function object pointer is captured once here so that collect()
// never touches the Python parser or the builtins dict.
function makeCollector() {
    const ensure   = nfn('PyGILState_Ensure',              'int',     []);
    const release  = nfn('PyGILState_Release',             'void',    ['int']);
    // PyImport_AddModule returns a *borrowed* reference — no decRef needed.
    const addMod   = nfn('PyImport_AddModule',             'pointer', ['pointer']);
    const getAttr  = nfn('PyObject_GetAttrString',         'pointer', ['pointer', 'pointer']);
    // PyObject_CallObject(func, NULL) calls with no args (NULL args tuple).
    // Prefer this over PyObject_CallFunctionObjArgs which is variadic and
    // requires special ABI handling that NativeFunction does not provide.
    const callFn   = nfn('PyObject_CallObject',            'pointer', ['pointer', 'pointer']);
    const asUtf8   = nfn('PyUnicode_AsUTF8',               'pointer', ['pointer']);
    const decRef   = nfn('Py_DecRef',                      'void',    ['pointer']);

    // Grab and permanently hold a reference to _arena_capture so we never
    // need to look it up (or parse Python) again.
    const cMain    = Memory.allocUtf8String('__main__');
    const cFunc    = Memory.allocUtf8String('_arena_capture');

    const state0   = ensure();
    const mainMod  = addMod(cMain);           // borrowed — no decRef
    const funcObj  = getAttr(mainMod, cFunc); // new ref — held for lifetime
    release(state0);

    if (funcObj.isNull()) return null;

    return function collect() {
        const state  = ensure();
        const result = callFn(funcObj, ptr('0x0'));   // _arena_capture() → str
        const cstr   = result.isNull() ? ptr('0x0') : asUtf8(result);
        const text   = cstr.isNull() ? '' : cstr.readUtf8String();
        if (!result.isNull()) decRef(result);
        release(state);
        return text;
    };
}

rpc.exports = {
    setup: function() {
        let run;
        try {
            run = makeSetupRunner();
        } catch (e) {
            return {ok: false, error: e.message};
        }

        // Define _arena_capture() once.  It captures C-level stderr via an OS
        // pipe (sys._debugmallocstats writes to fd 2 directly, bypassing
        // Python's sys.stderr) and returns the decoded text.
        const ret = run(`
import sys as _sys, os as _os

def _arena_capture():
    fd2  = _os.dup(2)
    r, w = _os.pipe()
    _os.dup2(w, 2)
    _os.close(w)
    try:
        _sys._debugmallocstats()
    finally:
        _os.dup2(fd2, 2)
        _os.close(fd2)
    data = b''
    while True:
        chunk = _os.read(r, 65536)
        if not chunk:
            break
        data += chunk
    _os.close(r)
    return data.decode()
`);
        if (ret !== 0) return {ok: false, error: 'failed to define _arena_capture'};

        try {
            _collect = makeCollector();
        } catch (e) {
            return {ok: false, error: e.message};
        }
        if (!_collect) return {ok: false, error: 'could not get _arena_capture reference'};
        return {ok: true};
    },

    collect: function() {
        if (!_collect) return {ok: false, error: 'call setup() first'};
        return {ok: true, text: _collect()};
    },
};
"""
