"""
browser_worker.py — Playwright CDP automation
100% runtime capture via Chrome DevTools Protocol
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright

async def run_with_cdp(html_content: str, timeout: int = 90) -> dict:
    """
    Run HTML in headless Chromium with CDP instrumentation.
    Captures ALL runtime data without modifying any JS source.
    """
    capture_data = {
        'strings': [],
        'network': [],
        'console_logs': [],
        'scripts_executed': [],
        'exceptions': [],
        'cdp_events': []
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-zygote',
                '--disable-web-security',
                '--allow-file-access-from-files'
            ]
        )

        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        page = await context.new_page()

        # ── CDP Session ──────────────────────────────────────
        client = await context.new_cdp_session(page)

        # Enable necessary CDP domains
        await client.send('Runtime.enable')
        await client.send('Debugger.enable')
        await client.send('Network.enable')
        await client.send('Log.enable')

        # ── CDP Hook 1: Runtime.consoleAPICalled ─────────────
        def on_console(event):
            args = event.get('args', [])
            for arg in args:
                val = arg.get('value') or arg.get('description', '')
                if val and isinstance(val, str) and len(val) > 1:
                    capture_data['console_logs'].append(str(val)[:1000])

        client.on('Runtime.consoleAPICalled', on_console)

        # ── CDP Hook 2: Network.responseReceived ─────────────
        def on_response(event):
            capture_data['network'].append({
                'type': 'response',
                'url': event.get('response', {}).get('url', ''),
                'status': event.get('response', {}).get('status', 0),
                'mimeType': event.get('response', {}).get('mimeType', '')
            })

        client.on('Network.responseReceived', on_response)

        # ── CDP Hook 3: Runtime.exceptionThrown ──────────────
        def on_exception(event):
            exc = event.get('exceptionDetails', {})
            capture_data['exceptions'].append({
                'text': exc.get('text', ''),
                'line': exc.get('lineNumber', 0)
            })

        client.on('Runtime.exceptionThrown', on_exception)

        # ── CDP Hook 4: Debugger - Script Source ─────────────
        # This captures eval'd code and dynamic scripts
        async def on_script_parsed(event):
            url = event.get('url', '')
            script_id = event.get('scriptId', '')
            if not url and script_id:  # dynamic/eval'd script
                try:
                    src = await client.send('Debugger.getScriptSource', {'scriptId': script_id})
                    source = src.get('scriptSource', '')
                    if source and len(source) > 50:
                        capture_data['scripts_executed'].append({
                            'scriptId': script_id,
                            'source': source[:5000],
                            'len': len(source)
                        })
                except:
                    pass

        client.on('Debugger.scriptParsed', lambda e: asyncio.create_task(on_script_parsed(e)))

        # ── CDP Hook 5: Runtime.bindingCalled ────────────────
        # Install bindings to capture string decryptions from inside JS
        await client.send('Runtime.addBinding', {'name': '__cdpCapture'})

        def on_binding(event):
            if event.get('name') == '__cdpCapture':
                try:
                    data = json.loads(event.get('payload', '{}'))
                    capture_data['strings'].append(data)
                except:
                    capture_data['strings'].append({'raw': event.get('payload', '')[:500]})

        client.on('Runtime.bindingCalled', on_binding)

        # ── Inject CDP binding hooks ──────────────────────────
        init_script = """
        window.__cdpCapture = window.__cdpCapture || function(){};

        // Hook String.fromCharCode
        const _fcc = String.fromCharCode;
        String.fromCharCode = function(...args) {
            const r = _fcc.apply(String, args);
            if (args.length > 2) {
                try { __cdpCapture(JSON.stringify({type:'fromCharCode', val:r.slice(0,500)})); } catch(e) {}
            }
            return r;
        };

        // Hook decodeURIComponent
        const _duri = decodeURIComponent;
        window.decodeURIComponent = function(s) {
            let r; try { r = _duri(s); } catch(e) { r = s; }
            if (r && r.length > 1) {
                try { __cdpCapture(JSON.stringify({type:'decodeURI', val:r.slice(0,500)})); } catch(e) {}
            }
            return r;
        };

        // Hook atob
        const _atob = window.atob;
        window.atob = function(s) {
            const r = _atob(s);
            try { __cdpCapture(JSON.stringify({type:'atob', in:s.slice(0,100), out:r.slice(0,500)})); } catch(e) {}
            return r;
        };

        // Hook JSON.parse
        const _jp = JSON.parse;
        JSON.parse = function(s) {
            const r = _jp(s);
            if (s && s.length > 10) {
                try { __cdpCapture(JSON.stringify({type:'jsonParse', in:String(s).slice(0,300), out:JSON.stringify(r).slice(0,300)})); } catch(e) {}
            }
            return r;
        };

        // Hook eval
        const _ev = window.eval;
        window.eval = function(code) {
            if (typeof code === 'string' && code.length > 50) {
                try { __cdpCapture(JSON.stringify({type:'eval', code:code.slice(0,3000), len:code.length})); } catch(e) {}
            }
            return _ev(code);
        };

        // Hook fetch
        const _ft = window.fetch;
        if (_ft) {
            window.fetch = async function(url, opts) {
                try { __cdpCapture(JSON.stringify({type:'fetch', url:String(url), method:(opts&&opts.method)||'GET'})); } catch(e) {}
                const res = await _ft(url, opts);
                const cl = res.clone();
                try {
                    const tx = await cl.text();
                    __cdpCapture(JSON.stringify({type:'fetchResponse', url:String(url), status:res.status, body:tx.slice(0,3000)}));
                } catch(e) {}
                return res;
            };
        }

        // Hook XHR
        const _XHR = window.XMLHttpRequest;
        window.XMLHttpRequest = function() {
            const xhr = new _XHR();
            const _o = xhr.open.bind(xhr);
            const _s = xhr.send.bind(xhr);
            let _method = '', _url = '';
            xhr.open = function(m, u, ...r) { _method=m; _url=u; return _o(m, u, ...r); };
            xhr.send = function(body) {
                try { __cdpCapture(JSON.stringify({type:'xhr', method:_method, url:_url, body:body?String(body).slice(0,500):null})); } catch(e) {}
                xhr.addEventListener('load', function() {
                    try { __cdpCapture(JSON.stringify({type:'xhrResponse', url:_url, status:xhr.status, body:xhr.responseText?xhr.responseText.slice(0,3000):null})); } catch(e) {}
                });
                return _s(body);
            };
            return xhr;
        };

        // localStorage hook
        const _lsg = localStorage.getItem.bind(localStorage);
        const _lss = localStorage.setItem.bind(localStorage);
        localStorage.getItem = function(k) {
            const v = _lsg(k);
            try { __cdpCapture(JSON.stringify({type:'lsGet', key:k, val:v})); } catch(e) {}
            return v;
        };
        localStorage.setItem = function(k, v) {
            try { __cdpCapture(JSON.stringify({type:'lsSet', key:k, val:String(v).slice(0,500)})); } catch(e) {}
            return _lss(k, v);
        };

        // Storage clear block
        Storage.prototype.clear = function() { console.log('Storage.clear blocked'); };

        // DevTools spoof
        try {
            Object.defineProperty(window, 'outerWidth',  { get: () => innerWidth,  configurable: true });
            Object.defineProperty(window, 'outerHeight', { get: () => innerHeight, configurable: true });
        } catch(e) {}

        console.log('😈 CDP HOOKS ACTIVE');
        """

        await context.add_init_script(init_script)

        # ── Console messages ──────────────────────────────────
        page.on('console', lambda msg: capture_data['console_logs'].append(f"[{msg.type}] {msg.text[:500]}"))

        # ── Load the HTML ─────────────────────────────────────
        await page.set_content(html_content, wait_until='domcontentloaded')

        # ── Wait for VM to run ────────────────────────────────
        print(f"⏳ Waiting {timeout}s for VM execution...")
        await asyncio.sleep(timeout)

        # ── Get network responses ─────────────────────────────
        try:
            for net_entry in capture_data['network']:
                url = net_entry.get('url', '')
                if url and net_entry.get('status', 0) == 200:
                    try:
                        response = await page.evaluate(f"""
                            fetch('{url}').then(r=>r.text()).catch(()=>'')
                        """)
                        net_entry['body'] = str(response)[:3000]
                    except:
                        pass
        except:
            pass

        await browser.close()

    # ── Process captured data ─────────────────────────────────
    unique_strings = []
    seen = set()
    for item in capture_data['strings']:
        if isinstance(item, dict):
            val = item.get('val') or item.get('out') or item.get('raw', '')
            if val and val not in seen and len(str(val)) > 1:
                seen.add(str(val))
                unique_strings.append(str(val))

    return {
        'unique_strings': unique_strings,
        'network': [x for x in capture_data['strings'] if isinstance(x, dict) and x.get('type') in ('fetch', 'fetchResponse', 'xhr', 'xhrResponse')],
        'storage': [x for x in capture_data['strings'] if isinstance(x, dict) and x.get('type') in ('lsGet', 'lsSet')],
        'eval_calls': [x for x in capture_data['strings'] if isinstance(x, dict) and x.get('type') == 'eval'],
        'scripts_executed': capture_data['scripts_executed'],
        'console_logs': capture_data['console_logs'],
        'exceptions': capture_data['exceptions'],
        'raw_events': capture_data['strings']
    }
