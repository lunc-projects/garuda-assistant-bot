"""Tests for the owner-alert throttler (2026-10-25).
Run: python3 test_alerts.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alerts as alerts_mod

fails = []
def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond: fails.append(name)

t = alerts_mod.AlertThrottler()
check("first alert goes out", t.allow("job:Timeout", 1000) is True)
check("same problem within the hour is suppressed", t.allow("job:Timeout", 2000) is False)
check("same problem after an hour alerts again", t.allow("job:Timeout", 1000 + 3601) is True)
check("different problem alerts right away", t.allow("handler:KeyError", 1500) is True)

t2 = alerts_mod.AlertThrottler()
sent = sum(1 for i in range(10) if t2.allow(f"k{i}:E", 5000))
check("global cap holds at 6 per hour", sent == 6)
check("global cap resets after the window", t2.allow("fresh:E", 5000 + 3601) is True)

# --- Transient gate (2026-10-26): 1st/2nd blip logged only, 3rd alerts ---
g = alerts_mod.TransientGate()
check("transient gate: 1st occurrence counts 1", g.note("job:NetworkError", 1000) == 1)
check("transient gate: 2nd occurrence counts 2", g.note("job:NetworkError", 1500) == 2)
check("transient gate: 3rd occurrence counts 3", g.note("job:NetworkError", 2000) == 3)
g.reset("job:NetworkError")
check("transient gate: counter resets after an alert", g.note("job:NetworkError", 2100) == 1)
check("transient gate: keys counted separately", g.note("job:ReadError", 2100) == 1)
g2 = alerts_mod.TransientGate()
g2.note("k:E", 1000)
check("transient gate: occurrences older than an hour fall out", g2.note("k:E", 1000 + 3601) == 1)

# --- Transient classification ---
class FakeNetErr(Exception): pass
FakeNetErr.__module__ = "telegram.error"
FakeNetErr.__name__ = "NetworkError"
class FakeReadErr(Exception): pass
FakeReadErr.__module__ = "httpx"
FakeReadErr.__name__ = "ReadError"
class FakeConnectErr(Exception): pass
FakeConnectErr.__module__ = "httpx"
FakeConnectErr.__name__ = "ConnectError"

check("classify: telegram NetworkError is transient", alerts_mod.is_transient_network_error(FakeNetErr("x")) is True)
check("classify: httpx ReadError is transient", alerts_mod.is_transient_network_error(FakeReadErr("x")) is True)
check("classify: httpx ConnectError is transient", alerts_mod.is_transient_network_error(FakeConnectErr("x")) is True)
try:
    try: raise FakeReadErr("boom")
    except FakeReadErr as inner: raise FakeNetErr("httpx.ReadError: ") from inner
except FakeNetErr as wrapped:
    check("classify: NetworkError wrapping an httpx error is transient",
          alerts_mod.is_transient_network_error(wrapped) is True)
check("classify: builtin TimeoutError is transient", alerts_mod.is_transient_network_error(TimeoutError("t")) is True)
check("classify: plain ValueError is NOT transient", alerts_mod.is_transient_network_error(ValueError("bad")) is False)
check("classify: KeyError is NOT transient", alerts_mod.is_transient_network_error(KeyError("k")) is False)

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
