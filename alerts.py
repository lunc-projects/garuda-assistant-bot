"""Owner alert throttling for the Garuda Assistant Bot (2026-10-25).

When something goes wrong inside the bot, the owner gets a DM — but
a repeating failure (a background job erroring every minute) must
not turn into alert spam. Rules:
- the same kind of problem alerts at most once per hour;
- total alerts are capped per rolling hour;
- record() is only called for an alert that will actually be sent,
  so suppressed problems stay suppressed until their window passes.
Pure and time-injected, so it's unit-testable.

Transient network blips (2026-10-26): a single dropped connection
used to page the owner even though the bot kept running fine.
is_transient_network_error() classifies those, and TransientGate
counts them per problem in a rolling hour — the caller logs the
1st/2nd occurrence and only alerts on the 3rd.
"""

try:
    import httpx as _httpx
except Exception:  # not importable in the unit-test env — name checks still apply
    _httpx = None

# httpx / httpcore transport-level failures (all subclass
# httpx.TransportError when the real library is present).
_TRANSIENT_NAMES = {
    "ReadError", "WriteError", "CloseError", "ConnectError",
    "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout",
    "RemoteProtocolError", "LocalProtocolError", "ProtocolError",
    "NetworkError", "TransportError", "TimeoutException",
}


def is_transient_network_error(err):
    """True for transient network blips: telegram.error.NetworkError
    (and its subclass TimedOut), the httpx/httpcore transport errors
    telegram wraps inside it, and asyncio/builtin timeouts.

    Walks the exception chain (__cause__, then __context__) because
    telegram usually raises NetworkError WRAPPING the httpx error;
    also checks the message text, since telegram formats the wrapped
    error into the string (e.g. "httpx.ReadError: ..."). Name/module
    checks are used instead of telegram imports so this stays
    dependency-free and unit-testable."""
    seen = set()
    cur = err
    hops = 0
    transport = getattr(_httpx, "TransportError", None) if _httpx else None
    while cur is not None and id(cur) not in seen and hops < 10:
        seen.add(id(cur))
        hops += 1
        if isinstance(cur, TimeoutError):
            return True
        if transport is not None and isinstance(cur, transport):
            return True
        name = type(cur).__name__
        mod = type(cur).__module__ or ""
        if name == "TimeoutError":
            return True
        if mod.startswith("telegram") and name in ("NetworkError", "TimedOut"):
            return True
        if (mod.startswith("httpx") or mod.startswith("httpcore")) and name in _TRANSIENT_NAMES:
            return True
        text = str(cur)
        if "httpx." in text or "httpcore." in text:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


class TransientGate:
    """Rolling-window occurrence counter for transient errors.
    note() records an occurrence and returns how many times this key
    has occurred inside the window (including this one); reset()
    clears a key once an alert has fired for it."""

    def __init__(self, window=3600):
        self.window = window
        self._hits = {}

    def note(self, key, now):
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        hits.append(now)
        self._hits[key] = hits
        return len(hits)

    def reset(self, key):
        self._hits.pop(key, None)


class AlertThrottler:
    def __init__(self, per_key_seconds=3600, global_max=6, global_window=3600):
        self.per_key_seconds = per_key_seconds
        self.global_max = global_max
        self.global_window = global_window
        self._last_by_key = {}
        self._sent = []

    def allow(self, key, now):
        """True (and records the send) if this alert may go out."""
        self._sent = [t for t in self._sent if now - t < self.global_window]
        last = self._last_by_key.get(key)
        if last is not None and now - last < self.per_key_seconds:
            return False
        if len(self._sent) >= self.global_max:
            return False
        self._last_by_key[key] = now
        self._sent.append(now)
        return True
