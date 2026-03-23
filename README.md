# zap-allocator

Dumps detailed stats about memory pools in a running Python interpreter
(supports 3.9-3.14, but does not support running under or against a
freethreading build at the moment).

Sould print something like

```
$ zap-allocator 69054
PID 69054  │  snapshot 1  │  89 arenas × 1 MiB  (highwater 143)

  size  pools    in_use   fill%
───────────────────────────────
    16      2       126    6.2%
    32      7     1,717   48.1%
    48     33    10,172   90.7%
    64     63    16,046   99.9%
    80   4939  1,007,390  100.0%
    96      9     1,489   97.3%
   112      6       858   98.6%
   128     10     1,170   92.1%
   144      3       286   84.4%
   160     27     2,723   98.9%
   176      3       219   79.3%
   192      2       150   88.2%
   208      9       653   93.0%
   224      6       395   91.4%
   240      5       335   98.5%
   256      6       353   93.4%
   272      5       283   94.3%
   288      7       388   99.0%
   304      4       167   78.8%
   320      4       185   90.7%
   336      4       151   78.6%
   352      3       131   94.9%
   368      3        97   73.5%
   384      3       105   83.3%
   400      8       299   93.4%
   416      2        73   93.6%
   432      2        65   87.8%
   448      2        61   84.7%
   464      2        44   62.9%
   480      2        55   80.9%
   496      2        53   82.8%
   512      2        59   95.2%

total: 1,046,298 blocks in use, 5,720 available
```


# Version Compat

This library is compatile with Python 3.10+, but should be linted under the
newest stable version.

# Versioning

This library follows [meanver](https://meanver.org/) which basically means
[semver](https://semver.org/) along with a promise to rename when the major
version changes.

# License

zap-allocator is copyright [Tim Hatch](https://timhatch.com/), and licensed under
the MIT license.  See the `LICENSE` file for details.
