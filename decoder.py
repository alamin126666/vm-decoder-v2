"""
decoder.py — Static decode + patch layer
"""
import re

# ── OUTER LAYER DECRYPT ─────────────────────────────────────
def decode_outer_layer(html: str) -> dict:
    """
    Outer encryption decode:
    - emjList symbol map build
    - pData JSON decode  
    - Base64 decode
    - Rolling XOR decrypt
    """
    import json, base64

    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    js = max(scripts, key=len) if scripts else ""

    # Check if outer encrypted (has emjList + pData)
    if '_emjList' not in js or '_pData' not in js:
        return {"decoded": False, "html": html, "js": js}

    try:
        std_b64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        emj_match = re.search(r'_emjList\s*=\s*(\[[^\]]+\])', js)
        emj_list = json.loads(emj_match.group(1))
        sym_map = {sym: std_b64[i] for i, sym in enumerate(emj_list) if i < len(std_b64)}
        sym_map['•'] = '='

        # Extract pData raw bytes
        raw = html.encode('utf-8')
        p_marker = b'const _pData = "'
        p_start = raw.find(p_marker) + len(p_marker)
        p_end = raw.find(b'";\n        const _sA', p_start)
        p_bytes = raw[p_start:p_end]
        p_data = json.loads('"' + p_bytes.decode('utf-8', errors='replace') + '"')

        # Build raw_b64
        raw_b64 = ""
        for ch in p_data:
            raw_b64 += sym_map.get(ch, ch if ch in std_b64 + "=" else '')

        # Base64 decode
        padded = raw_b64 + '=' * (-len(raw_b64) % 4)
        bin_data = base64.b64decode(padded)

        # Get keys
        sA_m = re.search(r'const _sA = (\d+)', js)
        sB_m = re.search(r'const _sB = (\d+)', js)
        sC_m = re.search(r'const _sC = (\d+)', js)
        sA = int(sA_m.group(1)) if sA_m else 68
        sB = int(sB_m.group(1)) if sB_m else 42
        sC = int(sC_m.group(1)) if sC_m else 32

        # Rolling XOR decrypt
        out = bytearray(len(bin_data))
        curA, curB = sA, sB
        for k in range(len(bin_data)):
            val = bin_data[k]
            val = (val ^ (k & 255)) & 255
            val = (val - curB + 256) & 255
            val = (val ^ curA) & 255
            out[k] = val
            curA = (curA * 3 + sC) & 255
            curB = (curB + 19) & 255

        decoded_html = out.decode('utf-8', errors='replace')
        return {"decoded": True, "html": decoded_html, "js": ""}

    except Exception as e:
        return {"decoded": False, "html": html, "js": js, "error": str(e)}


# ── ANTI-DEBUG PATCH ────────────────────────────────────────
def apply_patches(html: str) -> str:
    """Remove all anti-debug blocks"""

    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    if not scripts:
        return html
    js = max(scripts, key=len)
    patched = js

    def find_func_end(code, marker):
        idx = code.find(marker)
        if idx < 0: return -1, -1
        ob = code.index('{', idx)
        depth = 0
        for i in range(ob, len(code)):
            if code[i] == '{': depth += 1
            elif code[i] == '}':
                depth -= 1
                if depth == 0: return idx, i + 1
        return idx, -1

    patches = []

    # 1. DevTools detector → false
    s, e = find_func_end(patched, '$Ia9114c95=function(){')
    if e > 0:
        patched = patched[:s] + '$Ia9114c95=function(){ return false; }' + patched[e:]
        patches.append("DevTools detector → disabled")

    # 2. Destroy function → no-op
    s2, e2 = find_func_end(patched, 'var $O00585df1=function(){')
    if e2 > 0:
        patched = patched[:s2] + 'var $O00585df1=function(){ return; }' + patched[e2:]
        patches.append("Destroy function → no-op")

    # 3. console.clear → no-op
    patched = patched.replace(
        'console.clear&&console.clear();',
        'console.clear&&(function(){})();'
    )
    patches.append("console.clear → blocked")

    # 4. Redirect → blocked
    patched = re.sub(
        r'location\.replace\([^)]+\);',
        'console.log("redirect blocked");',
        patched
    )
    patched = re.sub(
        r'location\.href\s*=\s*\$l981e36ea\([^)]+\);',
        'console.log("href blocked");',
        patched
    )
    patches.append("Redirect → blocked")

    # 5. debugger timing → neutered
    patched = re.sub(
        r'var \$[A-Za-z0-9]+\s*=\s*performance\.now\(\);debugger;var \$[A-Za-z0-9]+\s*=\s*performance\.now\(\)[^;]+;if\([^)]+>800\)[^;]+;',
        '',
        patched
    )
    patches.append("debugger timing → neutered")

    # 6. Console CSS trick → no-op
    s3, e3 = find_func_end(patched, 'var $qcd1ef795=function(){')
    if e3 > 0:
        patched = patched[:s3] + 'var $qcd1ef795=function(){ return; }' + patched[e3:]
        patches.append("Console CSS trick → no-op")

    # 7. Native code checker → false
    patched = re.sub(
        r'\$Q201d15f8=function\(f\)\{var _r=false;.*?return _r;\};',
        '$Q201d15f8=function(f){ return false; };',
        patched,
        flags=re.DOTALL
    )
    patches.append("Native code checker → false")

    # 8. Hide Node.js
    patched = patched.replace(
        "typeof process!=='undefined'&&process&&process.versions&&process.versions.node",
        'false'
    )

    # Replace in HTML
    result = html.replace(js, patched)
    return result, patches


# ── CAPTURE SCRIPT INJECT ───────────────────────────────────
CAPTURE_SCRIPT = """
/* 😈 UNIVERSAL VM CAPTURER — CDP Enhanced */
(function() {
  window.__UC__ = {
    fromCharCode:[], decodeURI:[], atob:[], jsonParse:[],
    evalCalls:[], fetch:[], xhr:[], ws:[],
    localStorage:[], functionCalls:[], stackPushes:[],
    startTime: Date.now(), active: true
  };
  const C = window.__UC__;

  // Safety
  try { Storage.prototype.clear = function(){ return; }; } catch(e) {}
  try {
    Object.defineProperty(window,'outerWidth',{get:()=>window.innerWidth,configurable:true});
    Object.defineProperty(window,'outerHeight',{get:()=>window.innerHeight,configurable:true});
  } catch(e) {}
  window.stop = ()=>{};

  // Hooks
  const _fcc = String.fromCharCode;
  String.fromCharCode = function(...a){ const r=_fcc.apply(String,a); if(C.active&&a.length>2) C.fromCharCode.push(r.slice(0,500)); return r; };

  const _duri = decodeURIComponent;
  window.decodeURIComponent = function(s){ let r; try{r=_duri(s);}catch(e){r=s;} if(C.active&&r&&r.length>1) C.decodeURI.push(r.slice(0,500)); return r; };

  const _atob = window.atob;
  window.atob = function(s){ const r=_atob(s); if(C.active) C.atob.push({in:s.slice(0,100),out:r.slice(0,500)}); return r; };

  const _jp = JSON.parse;
  JSON.parse = function(s){ const r=_jp(s); if(C.active&&s&&s.length>2) C.jsonParse.push({in:String(s).slice(0,300),out:JSON.stringify(r).slice(0,300)}); return r; };

  const _ev = window.eval;
  window.eval = function(c){ if(C.active&&typeof c==='string') C.evalCalls.push(c.slice(0,2000)); return _ev(c); };

  const _ft = window.fetch;
  if(_ft) window.fetch = async function(url,opts){
    const e={url:String(url),method:(opts&&opts.method)||'GET',body:opts&&opts.body?String(opts.body).slice(0,500):null,t:Date.now()-C.startTime};
    C.fetch.push(e);
    try{ const res=await _ft(url,opts); const cl=res.clone(); try{const tx=await cl.text();e.response=tx.slice(0,3000);e.status=res.status;}catch(_){} return res; }catch(ex){ e.error=ex.message; throw ex; }
  };

  const _XHR = window.XMLHttpRequest;
  window.XMLHttpRequest = function(){
    const xhr=new _XHR(); const e={t:Date.now()-C.startTime}; C.xhr.push(e);
    const _o=xhr.open.bind(xhr); xhr.open=function(m,u,...r){e.method=m;e.url=u;return _o(m,u,...r);};
    const _s=xhr.send.bind(xhr); xhr.send=function(b){e.body=b?String(b).slice(0,500):null; xhr.addEventListener('load',function(){e.status=xhr.status;e.response=xhr.responseText?xhr.responseText.slice(0,3000):null;}); return _s(b);};
    return xhr;
  };

  const _lsg=localStorage.getItem.bind(localStorage);
  const _lss=localStorage.setItem.bind(localStorage);
  localStorage.getItem=function(k){const v=_lsg(k);if(C.active)C.localStorage.push({op:'get',k,v});return v;};
  localStorage.setItem=function(k,v){if(C.active)C.localStorage.push({op:'set',k,v:String(v).slice(0,500)});return _lss(k,v);};

  const _push=Array.prototype.push;
  let _d=0;
  Array.prototype.push=function(...a){
    if(C.active&&_d===0&&a.length===1&&this.length<200){
      const v=a[0],t=typeof v;
      if(t==='string'||t==='number'||t==='boolean'||v===null){
        _d++;C.stackPushes.push(t==='string'?v.slice(0,200):v);
        if(C.stackPushes.length>50000)C.stackPushes.shift();_d--;
      }
    }
    return _push.apply(this,a);
  };

  const _call=Function.prototype.call;
  let _cd=0;
  Function.prototype.call=function(th,...a){
    if(C.active&&_cd===0&&typeof this==='function'&&this.name&&this.name.length<80&&!this.name.startsWith('$')){
      _cd++;C.functionCalls.push({fn:this.name,t:Date.now()-C.startTime});
      if(C.functionCalls.length>10000)C.functionCalls.shift();_cd--;
    }
    return _call.apply(this,[th,...a]);
  };

  console.log('%c😈 UNIVERSAL CAPTURER ACTIVE!','color:#0f0;font-size:14px;font-weight:bold');

  window.__DOWNLOAD_CAPTURE__ = function(){
    C.active = false;
    const unique_strings = [...new Set([...C.fromCharCode,...C.decodeURI,...C.atob.map(x=>x.out)])];
    const report = {
      meta:{ capturedAt:new Date().toISOString(), url:location.href, title:document.title },
      summary:{ strings:unique_strings.length, fetch:C.fetch.length, xhr:C.xhr.length, localStorage:C.localStorage.length, evalCalls:C.evalCalls.length, functionCalls:C.functionCalls.length, stackPushes:C.stackPushes.length },
      unique_strings,
      network:{ fetch:C.fetch, xhr:C.xhr },
      storage:{ localStorage:C.localStorage },
      execution:{ evalCalls:C.evalCalls, functionCalls:C.functionCalls.slice(-3000) },
      vm_stack: C.stackPushes.slice(-10000)
    };
    const b=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(b);
    a.download='capture_'+Date.now()+'.json';
    document.body.appendChild(a);a.click();document.body.removeChild(a);
    console.log('%c✅ CAPTURE DOWNLOADED!','color:#0f0;font-size:14px;font-weight:bold');
  };
})();
"""

def inject_capture_script(html: str) -> str:
    """Inject universal capture script into HTML"""
    script_tag = f'<script>\n{CAPTURE_SCRIPT}\n</script>'
    if '<head>' in html:
        return html.replace('<head>', f'<head>\n{script_tag}', 1)
    elif '<body>' in html:
        return html.replace('<body>', f'<body>\n{script_tag}', 1)
    else:
        return script_tag + html


# ── JS RECONSTRUCT ──────────────────────────────────────────
def reconstruct_from_capture(capture_data: dict, original_html: str) -> str:
    """Reconstruct clean JS from runtime capture.
    Handles BOTH formats:
      - Manual JSON flow: network = {'fetch': [...], 'xhr': [...]}, storage = {'localStorage': [...]},
        execution = {'evalCalls': [...], 'functionCalls': [...]}
      - CDP flow:         network/storage are LISTS of typed events, execution absent
    """
    import json as json_lib

    strings = [str(s) for s in capture_data.get('unique_strings', []) if s is not None]
    network = capture_data.get('network', {})
    storage = capture_data.get('storage', {})
    execution = capture_data.get('execution', {})

    # ── Normalize network (list in CDP mode, dict in manual mode) ──
    if isinstance(network, list):
        fetch_calls, xhr_calls = [], []
        for x in network:
            if not isinstance(x, dict):
                continue
            t = x.get('type', '')
            if t in ('fetch', 'fetchResponse'):
                item = dict(x)
                # CDP stores fetched bodies under 'body' — expose as 'response' too
                if 'response' not in item and item.get('body'):
                    item['response'] = item['body']
                fetch_calls.append(item)
            elif t in ('xhr', 'xhrResponse'):
                item = dict(x)
                if 'response' not in item and item.get('body'):
                    item['response'] = item['body']
                xhr_calls.append(item)
    else:
        fetch_calls = network.get('fetch', []) if isinstance(network, dict) else []
        xhr_calls = network.get('xhr', []) if isinstance(network, dict) else []

    # ── Normalize storage (list in CDP mode, dict in manual mode) ──
    if isinstance(storage, list):
        ls_data = [x for x in storage if isinstance(x, dict)]
    else:
        ls_data = storage.get('localStorage', []) if isinstance(storage, dict) else []

    # CDP entries use {type:'lsGet'/'lsSet', key, val} — map to {op, k, v}
    norm_ls = []
    for x in ls_data:
        y = dict(x)
        t = y.get('type', '')
        if 'op' not in y:
            y['op'] = 'set' if t == 'lsSet' else 'get' if t == 'lsGet' else ''
        if 'k' not in y and 'key' in y:
            y['k'] = y['key']
        if 'v' not in y and 'val' in y:
            y['v'] = y['val']
        norm_ls.append(y)
    ls_data = norm_ls

    # ── Normalize execution (absent in CDP mode → use top-level eval_calls) ──
    if not isinstance(execution, dict) or not execution:
        execution = {
            'evalCalls': capture_data.get('eval_calls', []),
            'functionCalls': capture_data.get('function_calls', [])
        }

    # Extract key data
    apis = [s for s in strings if s.startswith('http')]
    keys = [s for s in strings if len(s) < 20 and s.isdigit() and len(s) >= 4]
    function_names = list({
        f.get('fn', '') for f in execution.get('functionCalls', [])
        if isinstance(f, dict) and f.get('fn') and not f['fn'].startswith('$')
    })
    eval_calls = execution.get('evalCalls', [])

    return {
        'apis': apis,
        'keys': keys,
        'functions': function_names,
        'fetch_calls': fetch_calls,
        'xhr_calls': xhr_calls,
        'localStorage': ls_data,
        'eval_calls': eval_calls,
        'eval_code': eval_calls,   # keep old key for backward compat
        'all_strings': strings
    }


# ── BODY + CSS EXTRACT ──────────────────────────────────────
def extract_body_css(html: str) -> str:
    """
    Extract only Body + CSS from HTML
    Remove all scripts completely
    """
    import re

    # Get CSS
    styles = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
    css = styles[0] if styles else ""

    # Get head (meta, title, links only — no scripts)
    head_match = re.search(r'<head[^>]*>(.*?)</head>', html, re.DOTALL)
    head_raw = head_match.group(1) if head_match else ""
    head_clean = re.sub(r'<script[^>]*>.*?</script>', '', head_raw, flags=re.DOTALL)
    head_clean = re.sub(r'<style[^>]*>.*?</style>', '', head_clean, flags=re.DOTALL)
    head_clean = head_clean.strip()

    # Get body (remove all scripts)
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body_raw = body_match.group(1) if body_match else html
    body_clean = re.sub(r'<script[^>]*>.*?</script>', '', body_raw, flags=re.DOTALL)
    body_clean = body_clean.strip()

    # Build clean HTML (body + css only)
    clean_html = f"""<!DOCTYPE html>
<html lang="bn">
<head>
{head_clean}
<style>
{css}
</style>
</head>
<body>
{body_clean}
<!-- ✅ Scripts removed — Body + CSS only -->
<!-- Send this file + runtime JSON to get final decoded HTML -->
</body>
</html>"""

    return clean_html
