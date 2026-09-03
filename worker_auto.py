"""IA Hoy worker automatico 2/dia - gratis GitHub Actions.
Busca en X con twifork, transcribe plantilla ES, imagen segun regla, publica en FB Page y verifica.
Secretos por env: FB_PAGE_TOKEN, X_AUTH_TOKEN, X_CT0. Nunca imprimir tokens.
"""
import os, json, pathlib, asyncio, random, datetime
import httpx
from PIL import Image, ImageDraw, ImageFont

BASE = pathlib.Path(__file__).parent
KEYWORDS = json.loads((BASE/"keywords.json").read_text(encoding="utf-8"))
DONE_PATH = BASE/"done.json"
PAGE_ID = os.environ.get("FB_PAGE_ID", "140179309177283")
GRAPH = "https://graph.facebook.com/v19.0"

def load_done():
    if DONE_PATH.exists():
        try:
            return set(json.loads(DONE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()

def save_done(s):
    DONE_PATH.write_text(json.dumps(sorted(s), ensure_ascii=False, indent=2), encoding="utf-8")

def build_caption(item):
    author = item["author"]
    url = item["url"]
    text = (item.get("full_text") or "")[:280].replace("\n", " ").strip()
    q = item.get("query", "IA")
    return f"""🤖 {q} — IA Hoy

En español: {text}

Por qué importa: novedad real desde X, te la resumimos para que no te pierdas ningún modelo.

¿Qué opinas? 👇

Fuente: Vía @{author} {url}
#IAHoy #IA #InteligenciaArtificial #TechNews"""

def make_cover(title, out_path):
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), (18, 18, 28))
    d = ImageDraw.Draw(img)
    # degradado simple
    for y in range(H):
        c = int(18 + y*40/H)
        d.line([(0, y), (W, y)], fill=(c, c+10, c+30))
    try:
        ft = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
        fs = ImageFont.truetype("DejaVuSans.ttf", 32)
    except Exception:
        ft = ImageFont.load_default(); fs = ImageFont.load_default()
    d.text((W//2, H//2-40), title[:40], fill=(255,255,255), font=ft, anchor="mm")
    d.text((W//2, H//2+60), "IA Hoy | Noticias IA", fill=(180,180,200), font=fs, anchor="mm")
    img.save(out_path, quality=90)
    return out_path

def frame_original(inp, outp, title, credit):
    img = Image.open(inp).convert("RGB")
    W, H = img.size
    th, bh = int(H*0.16), int(H*0.10)
    cv = Image.new("RGB", (W, H+th+bh), (12,12,18))
    d = ImageDraw.Draw(cv)
    try:
        ft = ImageFont.truetype("DejaVuSans-Bold.ttf", max(20, W//28))
        fs = ImageFont.truetype("DejaVuSans.ttf", max(14, W//55))
    except Exception:
        ft = ImageFont.load_default(); fs = ImageFont.load_default()
    cv.paste(img, (0, th))
    d.text((W//2, th//2), title[:60], fill=(255,255,255), font=ft, anchor="mm")
    d.text((W//2, H+th+bh//2), credit[:80], fill=(180,180,190), font=fs, anchor="mm")
    cv.save(outp, quality=92)
    return outp

async def fetch_one():
    from twikit import Client
    auth = os.environ.get("X_AUTH_TOKEN","").strip()
    ct0 = os.environ.get("X_CT0","").strip()
    if len(auth)<20 or len(ct0)<20:
        raise SystemExit("MISSING_X_SECRETS")
    done = load_done()
    queries = KEYWORDS.get("search_queries", ["inteligencia artificial"])[:]
    random.shuffle(queries)
    client = Client('en-US')
    client.set_cookies({"auth_token": auth, "ct0": ct0})
    for q in queries[:8]:
        try:
            tweets = await client.search_tweet(q, product='Top', count=5)
        except Exception as e:
            print(f"SEARCH_ERR {q} {type(e).__name__}"); continue
        for t in tweets or []:
            tid = str(getattr(t, 'id', ''))
            if not tid or tid in done:
                continue
            user = getattr(getattr(t,'user',None),'screen_name','?')
            media=[]
            try:
                for m in (t.media or [])[:2]:
                    for k in ('media_url_https','media_url','url','preview_image_url'):
                        v=m.get(k) if isinstance(m,dict) else getattr(m,k,None)
                        if v and isinstance(v,str) and v.startswith('http'):
                            media.append(v); break
            except Exception:
                pass
            return {"query":q,"id":tid,"url":getattr(t,'url','') or f"https://x.com/{user}/status/{tid}","author":user,"full_text":getattr(t,'full_text','') or getattr(t,'text',''),"media_urls":media}
    print("NO_NEW_FOUND")
    return None

def get_page_token(user_token):
    with httpx.Client(timeout=30) as c:
        r=c.get(f"{GRAPH}/me/accounts", params={"access_token":user_token,"fields":"id,access_token"})
        for p in r.json().get("data",[]):
            if str(p.get("id"))==PAGE_ID:
                return p["access_token"]
    return user_token

def publish(image_path, caption):
    fb = os.environ.get("FB_PAGE_TOKEN","").strip()
    if len(fb)<50:
        raise SystemExit("MISSING_FB_SECRET")
    print(f"TOKEN len={len(fb)}")
    pt = get_page_token(fb)
    with httpx.Client(timeout=60) as c:
        with open(image_path,"rb") as f:
            r=c.post(f"{GRAPH}/{PAGE_ID}/photos", data={"message":caption,"published":"true","access_token":pt}, files={"source":("ia.jpg",f,"image/jpeg")})
        print(f"UPLOAD {r.status_code} {r.text[:400]}")
        j=r.json(); pid=j.get("post_id") or j.get("id")
        if not pid:
            raise SystemExit(f"UPLOAD_FAILED {j}")
        r2=c.get(f"{GRAPH}/{pid}", params={"access_token":pt,"fields":"id,permalink_url,is_published"})
        print(f"READBACK {r2.status_code} {r2.text[:400]}")
        return pid

async def main():
    done=load_done()
    print(f"DONE count={len(done)}")
    item=await fetch_one()
    if not item:
        return
    print(f"NEW @{item['author']} {item['id']} q={item['query']}")
    out_dir=BASE/"final"; out_dir.mkdir(exist_ok=True)
    # imagen segun regla
    final_img=""
    if item["media_urls"]:
        u=item["media_urls"][0]
        orig=BASE/f"originals/{item['id']}.jpg"
        orig.parent.mkdir(exist_ok=True)
        with httpx.Client(timeout=60) as c:
            r=c.get(u); orig.write_bytes(r.content)
        if "video_thumb" in u or "amplify" in u:
            final_img=str(out_dir/f"{item['id']}_cover.jpg")
            make_cover(item["query"], final_img)
            # link video va en caption ya via url
        else:
            final_img=str(out_dir/f"{item['id']}_framed.jpg")
            frame_original(str(orig), final_img, f"{item['query']} — IA Hoy", f"Imagen: @{item['author']} en X | IA Hoy")
    else:
        final_img=str(out_dir/f"{item['id']}_cover.jpg")
        make_cover(item["query"], final_img)
    cap=build_caption(item)
    pid=publish(final_img, cap)
    done.add(item["id"])
    save_done(done)
    print(f"DONE_SAVED pid={pid}")

if __name__=="__main__":
    asyncio.run(main())
