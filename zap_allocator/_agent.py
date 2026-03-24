"""Frida JS agent injected into the target process.

Injected once via setup(); collect() can be called repeatedly.

Capture strategy: call _PyObject_DebugMallocStats() directly from native code,
passing an open_memstream() FILE* instead of stderr.  This avoids any fd
redirection — we never touch fd 2, never create a pipe, and never inject
Python source into the target.

Symbol resolution:
  Fast path — sym() scans dynsym across all loaded modules.  Works for
              framework/shared-library builds where the symbol is exported.
  Slow path — if the symbol is absent from dynsym (stripped or static build),
              ask ctypes.pythonapi inside the target process.  pythonapi opens
              the Python runtime DLL directly via its known path, so it finds
              internal symbols that were never placed in the global symbol table.
"""

from __future__ import annotations

_AGENT_JS = r"""
'use strict';

let _collectFn = null;

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

// Locate _PyObject_DebugMallocStats, trying two strategies:
//
//   1. sym() — fast, zero overhead, covers exported symbols.
//
//   2. ctypes.pythonapi fallback — if the symbol is not in dynsym, inject a
//      one-liner into the target that uses ctypes.pythonapi (which dlopen()s
//      the Python runtime by its known path) to retrieve the address.
//      The result is stored on __main__ as a plain int, then read back via
//      PyLong_AsVoidPtr so we never need to parse or allocate anything.
function findDebugMallocStats(ensure, release) {
    const p = sym('_PyObject_DebugMallocStats');
    if (p) return p;

    // Slow path: ask ctypes inside the target.
    const runStr  = nfn('PyRun_SimpleString',     'int',     ['pointer']);
    const addMod  = nfn('PyImport_AddModule',     'pointer', ['pointer']);
    const getAttr = nfn('PyObject_GetAttrString', 'pointer', ['pointer', 'pointer']);
    const delAttr = nfn('PyObject_DelAttrString', 'int',     ['pointer', 'pointer']);
    const asVoidP = nfn('PyLong_AsVoidPtr',       'pointer', ['pointer']);
    const decRef  = nfn('Py_DecRef',              'void',    ['pointer']);

    const state = ensure();
    // ctypes.pythonapi opens the Python runtime DLL directly — it can resolve
    // _PyObject_DebugMallocStats even when it has hidden ELF visibility,
    // because pythonapi bypasses the global symbol table and goes straight to
    // the runtime's own export table.
    runStr(Memory.allocUtf8String(
        'import ctypes as _ct, __main__ as _m;' +
        '_m._dms_addr = _ct.cast(' +
        '    _ct.pythonapi._PyObject_DebugMallocStats, _ct.c_void_p).value'
    ));
    const cMain   = Memory.allocUtf8String('__main__');
    const cAttr   = Memory.allocUtf8String('_dms_addr');
    const main    = addMod(cMain);
    const addrObj = getAttr(main, cAttr);
    const addrPtr = (addrObj && !addrObj.isNull()) ? asVoidP(addrObj) : ptr(0);
    if (addrObj && !addrObj.isNull()) decRef(addrObj);
    delAttr(main, cAttr);  // clean up scratchpad attribute
    release(state);

    return (addrPtr && !addrPtr.isNull()) ? addrPtr : null;
}

// Build a collect() closure.
// _PyObject_DebugMallocStats(FILE *out) writes all pymalloc stats to *out*.
// open_memstream() gives us a FILE* backed by a heap buffer that grows as
// needed and is always null-terminated after fclose().  We pass that in,
// then read back the text without ever touching stderr or any file descriptor.
function makeCollector() {
    const ensure     = nfn('PyGILState_Ensure',  'int',     []);
    const release    = nfn('PyGILState_Release', 'void',    ['int']);
    const openMem    = nfn('open_memstream',     'pointer', ['pointer', 'pointer']);
    const fclose     = nfn('fclose',             'int',     ['pointer']);
    const free       = nfn('free',               'void',    ['pointer']);

    const debugStatsPtr = findDebugMallocStats(ensure, release);
    if (!debugStatsPtr) throw new Error('could not locate _PyObject_DebugMallocStats');
    const debugStats = new NativeFunction(debugStatsPtr, 'void', ['pointer']);

    return function collect() {
        // open_memstream writes buf/size through these two pointers.
        // The buffer is always null-terminated after fclose(), so we only
        // need bufPtrPtr; sizePtrPtr is passed because the API requires it.
        const bufPtrPtr  = Memory.alloc(Process.pointerSize);
        const sizePtrPtr = Memory.alloc(Process.pointerSize);

        const fp = openMem(bufPtrPtr, sizePtrPtr);
        if (fp.isNull()) return '';

        // GIL is needed for _PyObject_DebugMallocStats; fclose/free are plain C.
        const state = ensure();
        debugStats(fp);
        release(state);

        fclose(fp);  // flushes and finalises the null terminator

        const bufPtr = bufPtrPtr.readPointer();
        const text   = (bufPtr && !bufPtr.isNull()) ? bufPtr.readUtf8String() : '';
        if (bufPtr && !bufPtr.isNull()) free(bufPtr);
        return text;
    };
}

rpc.exports = {
    setup: function() {
        try {
            _collectFn = makeCollector();
        } catch (e) {
            return {ok: false, error: e.message};
        }
        return {ok: true};
    },

    collect: function() {
        if (!_collectFn) return {ok: false, error: 'call setup() first'};
        try {
            return {ok: true, text: _collectFn()};
        } catch (e) {
            return {ok: false, error: e.message};
        }
    },
};
"""
