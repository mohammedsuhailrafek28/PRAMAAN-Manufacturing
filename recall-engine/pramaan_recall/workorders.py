"""Work-order obligations and computed reconciliation.

Reconciliation is computed from the component/inspection events, never taken
from a WORK_ORDER_CLOSED disposition.
"""


def reconcile(active):
    """-> {workOrderId: {...}} built from active (non-superseded) events."""
    wos = {}
    for e in active:
        t, wid = e["eventType"], e.get("workOrderId")
        if t == "WORK_ORDER_OPENED":
            p = e["payload"]
            wos[e["workOrderId"]] = dict(
                workOrderId=wid, orderType=p.get("orderType"), status="OPEN",
                disposition=None, openedEventId=e["eventId"], closedEventId=None,
                closedAt=None, expected=p.get("expectedChanges", []),
                obligations=[], unexpected=[], eventIds=[e["eventId"]])
    for e in active:
        if e["eventType"] == "WORK_ORDER_CLOSED" and e.get("workOrderId") in wos:
            w = wos[e["workOrderId"]]
            w.update(status="CLOSED", disposition=e["payload"].get("disposition"),
                     closedEventId=e["eventId"], closedAt=e["occurredAt"])
            w["eventIds"].append(e["eventId"])

    removed, installed, inspected, orphans = {}, {}, {}, []
    for e in active:
        t, wid = e["eventType"], e.get("workOrderId")
        if t not in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED", "INSPECTION_RECORDED"):
            continue
        if wid not in wos:
            orphans.append(e["eventId"])
            continue
        wos[wid]["eventIds"].append(e["eventId"])
        slot = e["payload"].get("slot")
        if t == "COMPONENT_INSTALLED":
            installed.setdefault((wid, slot), []).append(e)
        elif t == "COMPONENT_REMOVED":
            removed.setdefault((wid, slot), []).append(e)
        else:
            inspected.setdefault(wid, []).append(e)

    for wid, w in wos.items():
        done = w["status"] == "CLOSED"
        for ch in w["expected"]:
            slot, action = ch["slot"], ch["action"]
            ins, rem = installed.get((wid, slot), []), removed.get((wid, slot), [])
            if action == "INSTALL":
                ev = ins
            elif action == "REMOVE":
                ev = rem
            elif action == "REPLACE":
                ev = (rem + ins) if rem and any(
                    i["occurredAt"] >= r["occurredAt"] for r in rem for i in ins) else []
            elif action == "INSPECT":
                ev = [i for i in inspected.get(wid, [])
                      if any(str(s).startswith(slot) for s in i["payload"].get("scope", [slot]))]
            else:
                ev = []
            status = "MET" if ev else ("UNMET" if done else "PENDING")
            w["obligations"].append(dict(slot=slot, action=action, status=status,
                                         satisfiedBy=[x["eventId"] for x in ev]))
        w["reconciliation"] = ("RECONCILED" if all(o["status"] == "MET" for o in w["obligations"])
                               else "UNRECONCILED")
    for (wid, slot), evs in list(installed.items()) + list(removed.items()):
        if slot not in {c["slot"] for c in wos[wid]["expected"]}:
            wos[wid]["unexpected"].extend(x["eventId"] for x in evs)
    return dict(workOrders=wos, orphanEventIds=orphans)
