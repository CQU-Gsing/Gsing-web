"""Read-only visitor analytics, with parameterized filters and Beijing times."""
from collections import defaultdict
from datetime import datetime, timedelta
from src.storage import CHINA_TIME
from src.ip_location import is_internal_ip, query_ip_location


def build_analytics(store, query=""):
    where = " WHERE instr(ip,?)>0 OR instr(location,?)>0 OR instr(username,?)>0" if query else ""
    params = [query]*3 if query else []
    with store.connect() as db:
        totals = dict(db.execute("SELECT COUNT(*) AS requests, COUNT(DISTINCT ip) AS ips, COALESCE(SUM(status>=400),0) AS errors FROM visits"+where,params).fetchone())
        ips = [dict(row) for row in db.execute("SELECT ip,COUNT(*) AS requests, GROUP_CONCAT(DISTINCT username) AS users, datetime(MAX(visited_at),'+8 hours') AS last_seen FROM visits"+where+" GROUP BY ip ORDER BY requests DESC,ip",params)]
        paths = [dict(row) for row in db.execute("SELECT path,COUNT(*) AS requests FROM visits"+where+" GROUP BY path ORDER BY requests DESC,path LIMIT 12",params)]
        today=datetime.now(CHINA_TIME).date()
        first=(today-timedelta(days=29)).isoformat()
        trend_where = (" WHERE (instr(ip,?)>0 OR instr(location,?)>0 OR instr(username,?)>0) AND" if query else " WHERE")
        daily = dict(db.execute("SELECT date(visited_at,'+8 hours'),COUNT(*) FROM visits"+trend_where+" date(visited_at,'+8 hours') BETWEEN ? AND ? GROUP BY date(visited_at,'+8 hours')",params+[first,today.isoformat()]).fetchall())
    groups = {"domestic":defaultdict(list),"overseas":defaultdict(list),"internal":defaultdict(list),"unknown":defaultdict(list)}
    totals["domestic"] = 0
    for item in ips:
        if is_internal_ip(item["ip"]):
            group,label="internal","本地 / 内网"
        else:
            location=query_ip_location(item["ip"])
            country=location.get("country") or "未知"
            if country in {"中国","China","中国大陆"}:
                group,label="domestic",location.get("region") or location.get("city") or "中国（省份未知）"
                totals["domestic"]+=item["requests"]
            elif country in {"未知","本机/内网"}:
                group,label="unknown","归属地未知"
            else:
                group,label="overseas",country
        item["region"]=label
        groups[group][label].append(item)
    regions={key:sorted([{"label":label,"requests":sum(i["requests"] for i in entries),"entries":entries} for label,entries in values.items()],key=lambda r:(-r["requests"],r["label"])) for key,values in groups.items()}
    trend=[{"date":(today-timedelta(days=offset)).isoformat(),"requests":daily.get((today-timedelta(days=offset)).isoformat(),0)} for offset in range(29,-1,-1)]
    peak=max(1,max(day["requests"] for day in trend))
    return {"totals":totals,"regions":regions,"ips":ips[:20],"paths":paths,"trend":trend,"peak":peak,"generated_at":datetime.now(CHINA_TIME).strftime("%Y-%m-%d %H:%M:%S")}


def visit_detail(store, ip, page=1):
    with store.connect() as db:
        total=db.execute("SELECT COUNT(*) FROM visits WHERE ip=?",(ip,)).fetchone()[0]
        pages=max(1,(total+49)//50)
        page=min(max(page,1),pages)
        rows=[dict(row) for row in db.execute("SELECT datetime(visited_at,'+8 hours') AS time,username,method,path,status,elapsed_ms,location,user_agent FROM visits WHERE ip=? ORDER BY id DESC LIMIT 50 OFFSET ?",(ip,(page-1)*50))]
    return {"ip":ip,"total":total,"rows":rows,"page":page,"pages":pages}
