import * as vscode from 'vscode';
import * as http from 'http';
import * as https from 'https';
import { spawn, ChildProcess, exec } from 'child_process';
import { Readable } from 'stream';
import { promisify } from 'util';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

// ─── Config ────────────────────────────────────────────────────────────────

interface CodexConfig {
    bridgeUrl: string;
    model: string;
    provider: string;
    maxTokens: number;
    inlineEnabled: boolean;
    autoStart: boolean;
}

function getConfig(): CodexConfig {
    const cfg = vscode.workspace.getConfiguration('codexLocal');
    return {
        bridgeUrl: cfg.get('bridgeUrl', 'http://127.0.0.1:8787'),
        model: cfg.get('model', 'deepseek-chat'),
        provider: cfg.get('provider', 'deepseek'),
        maxTokens: cfg.get('maxTokens', 200),
        inlineEnabled: cfg.get('inlineEnabled', true),
        autoStart: cfg.get('autoStart', true),
    };
}

// ─── Bridge Process Manager ────────────────────────────────────────────────

class BridgeManager {
    private process: ChildProcess | null = null;
    private pythonPath: string = '';
    private bridgePath: string = '';
    private status: 'stopped' | 'starting' | 'running' | 'error' = 'stopped';
    private listeners: Set<(status: string, info: any) => void> = new Set();

    constructor() {
        this.findPython();
        this.findBridge();
    }

    private findPython(): void {
        const candidates = [
            'python', 'python3',
            'C:/Python314/python', 'C:/Python313/python', 'C:/Python312/python',
            'C:/Program Files/Python311/python',
            process.env.PYTHON_PATH || '',
        ].filter(Boolean);

        for (const py of candidates) {
            try {
                // quick check - don't actually run python
                this.pythonPath = py;
                break;
            } catch { }
        }
        if (!this.pythonPath) this.pythonPath = 'python';
    }

    private findBridge(): void {
        const candidates = [
            path.join(process.cwd(), '..', 'bridge.py'),
            path.join(process.cwd(), '..', 'runtime', '..', 'bridge.py'),
            'D:/codex-local/bridge.py',
            'C:/Users/lenovo/codex-local/bridge.py',
        ];
        for (const p of candidates) {
            if (fs.existsSync(p)) {
                this.bridgePath = p;
                return;
            }
        }
    }

    onStatus(cb: (status: string, info: any) => void): void {
        this.listeners.add(cb);
    }

    private notify(status: string, info: any): void {
        this.listeners.forEach(cb => {
            try { cb(status, info); } catch { }
        });
    }

    async start(): Promise<void> {
        if (this.status === 'running') return;
        this.status = 'starting';
        this.notify('starting', {});

        return new Promise((resolve, reject) => {
            if (this.pythonPath && fs.existsSync(this.pythonPath)) {
                try {
                    this.process = spawn(this.pythonPath, [this.bridgePath], {
                        stdio: ['ignore', 'pipe', 'pipe'],
                        cwd: path.dirname(this.bridgePath) || process.cwd(),
                        detached: true,
                        env: { ...process.env as Record<string, string> },
                    });
                } catch (e) {
                    this.status = 'error';
                    this.notify('error', { error: String(e) });
                    reject(e);
                    return;
                }
            }

            this.process?.stdout?.on('data', (d: Buffer) => {
                vscode.window.showInformationMessage('[codex-local] ' + d.toString().trim());
            });

            this.process?.stderr?.on('data', (d: Buffer) => {
                vscode.window.showWarningMessage('[codex-local] ' + d.toString().trim());
            });

            this.process?.on('error', (e: Error) => {
                this.status = 'error';
                this.notify('error', { error: e.message });
                reject(e);
            });

            this.process?.on('exit', (code: number) => {
                this.status = 'stopped';
                if (code !== 0) {
                    this.notify('stopped', { code });
                }
            });

            // Wait for server to start
            setTimeout(() => {
                this.status = 'running';
                this.notify('running', { url: getConfig().bridgeUrl });
                resolve();
            }, 2000);
        });
    }

    stop(): void {
        if (this.process) {
            this.process.kill();
            this.process = null;
        }
        this.status = 'stopped';
        this.notify('stopped', {});
    }

    getStatus(): string {
        return this.status;
    }
}

// ─── HTTP Client ─────────────────────────────────────────────────────────

async function bridgeRequest(body: object): Promise<any> {
    const cfg = getConfig();
    const url = new URL(cfg.bridgeUrl + '/v1/responses');

    return new Promise((resolve, reject) => {
        const postData = JSON.stringify(body);
        const req = http.request({
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData),
            },
            timeout: 30000,
        }, (res) => {
            let data = '';
            res.on('data', chunk => { data += chunk; });
            res.on('end', () => {
                try {
                    resolve(JSON.parse(data));
                } catch {
                    resolve({ error: data });
                }
            });
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
        req.write(postData);
        req.end();
    });
}

// ─── Inline Completion Provider ─────────────────────────────────────────

class CodexInlineCompletionProvider implements vscode.InlineCompletionItemProvider {
    private bridgeManager: BridgeManager;

    constructor(bm: BridgeManager) {
        this.bridgeManager = bm;
    }

    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext,
        token: vscode.CancellationToken,
    ): Promise<vscode.InlineCompletionItem[]> {
        if (!getConfig().inlineEnabled) return [];
        if (this.bridgeManager.getStatus() !== 'running') return [];

        const cfg = getConfig();
        const textBefore = document.getText(new vscode.Range(
            new vscode.Position(Math.max(0, position.line - 20), 0),
            position,
        ));

        try {
            const result = await bridgeRequest({
                model: cfg.model,
                input: [
                    { role: 'system', content: 'You are Codex-Local inline completion. Complete the code. Return ONLY the completion, no explanation.' },
                    { role: 'user', content: `Complete this code:\n${textBefore}` },
                ],
                stream: false,
                max_output_tokens: cfg.maxTokens,
            });

            const items = this.parseResponse(result);
            return items;
        } catch {
            return [];
        }
    }

    private parseResponse(result: any): vscode.InlineCompletionItem[] {
        const items: vscode.InlineCompletionItem[] = [];
        try {
            for (const output of (result.output || [])) {
                if (output.type === 'message') {
                    const content = (output.content || [])
                        .filter((c: any) => c.type === 'output_text')
                        .map((c: any) => c.text || '')
                        .join('');
                    if (content) {
                        items.push(new vscode.InlineCompletionItem(content, new vscode.Range(0, 0, 0, 0));
                    }
                }
                if (output.type === 'function_call') {
                    // Skip tool calls in inline completion
                }
            }
        } catch { }
        return items;
    }
}

// ─── Chat Panel ─────────────────────────────────────────────────────────

class ChatPanel {
    private panel: vscode.WebviewPanel | null = null;
    private bridgeManager: BridgeManager;

    constructor(bm: BridgeManager) {
        this.bridgeManager = bm;
    }

    show(initialMessage?: string): void {
        if (this.panel) {
            this.panel.reveal();
            return;
        }

        this.panel = vscode.window.createWebviewPanel(
            'codexLocalChat',
            'Codex-Local Chat',
            vscode.ViewColumn.Two,
            { enableScripts: true, retainContextWhenHidden: true },
        );

        const initialHtml = this.getHtml();
        this.panel.webview.html = initialHtml;

        if (initialMessage) {
            this.sendMessage({ type: 'user', text: initialMessage });
        }

        this.panel.webview.onDidReceiveMessage(msg => {
            this.handleMessage(msg);
        });

        this.panel.onDidDispose(() => {
            this.panel = null;
        });
    }

    sendMessage(msg: { type: string; text?: string; }) {
        this.panel?.webview.postMessage(msg);
    }

    private async handleMessage(msg: any): Promise<void> {
        if (msg.type === 'user') {
            const cfg = getConfig();
            this.sendMessage({ type: 'thinking', text: 'Thinking...' });

            try {
                const result = await bridgeRequest({
                    model: cfg.model,
                    input: [
                        { role: 'system', content: 'You are Codex-Local. You help with coding tasks. Be concise and precise.' },
                        { role: 'user', content: msg.text },
                    ],
                    stream: false,
                    max_output_tokens: cfg.maxTokens * 4,
                });

                const reply = this.extractReply(result);
                this.sendMessage({ type: 'assistant', text: reply });
            } catch (e: any) {
                this.sendMessage({ type: 'error', text: e.message });
            }
        }
    }

    private extractReply(result: any): string {
        for (const output of (result.output || [])) {
            if (output.type === 'message') {
                for (const c of (output.content || [])) {
                    if (c.type === 'output_text') return c.text || '';
                }
            }
        }
        return 'No response from Codex-Local bridge. Is the bridge server running?';
    }

    private getHtml(): string {
        return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: #1e1e1e; color: #ccc; height: 100vh; display: flex; flex-direction: column; }
#toolbar { background: #252526; padding: 8px 12px; border-bottom: 1px solid #3c3c3c; display: flex; gap: 8px; align-items: center; }
#toolbar button { background: #0e639c; color: #fff; border: none; border-radius: 3px; padding: 4px 12px; cursor: pointer; font-size: 12px; }
#toolbar button:hover { background: #1177bb; }
.status { font-size: 11px; color: #888; margin-left: auto; }
.status.running { color: #4ec9b0; }
.status.stopped { color: #f14c4c; }
#messages { flex: 1; overflow-y: auto; padding: 12px; }
.msg { margin-bottom: 12px; display: flex; gap: 8px; }
.msg.user { flex-direction: row-reverse; }
.msg .bubble { max-width: 80%; padding: 8px 12px; border-radius: 8px; line-height: 1.5; white-space: pre-wrap; }
.msg.user .bubble { background: #0e639c; color: #fff; border-radius: 12px 12px 4px 12px; }
.msg.assistant .bubble { background: #2d2d30; border-radius: 12px 12px 12px 4px; }
.msg .bubble.error { background: #f14c4c20; color: #f48771; border: 1px solid #f14c4c40; }
#input-area { background: #252526; border-top: 1px solid #3c3c3c; padding: 8px; display: flex; gap: 8px; }
#input { flex: 1; background: #3c3c3c; border: 1px solid #3c3c3c; border-radius: 4px; color: #ccc; padding: 8px 12px; font-size: 13px; resize: none; outline: none; }
#input:focus { border-color: #0e639c; }
#send { background: #0e639c; color: #fff; border: none; border-radius: 4px; padding: 8px 16px; cursor: pointer; }
#send:hover { background: #1177bb; }
</style>
</head>
<body>
<div id="toolbar">
<button onclick="clearChat()">Clear</button>
<button onclick="restartBridge()">Restart Bridge</button>
<button onclick="runSelection()">Run Selection</button>
<div class="status stopped" id="status">Stopped</div>
</div>
<div id="messages"></div>
<div id="input-area">
<textarea id="input" placeholder="Ask Codex-Local..." rows="1"></textarea>
<button id="send" onclick="sendMessage()">Send</button>
</div>
<script>
const vscode = acquireVsCodeApi();
const statusEl = document.getElementById('status');
let bridgeStatus = 'stopped';

vscode.setState({ messages: [] });

function updateStatus(s, info) {
    bridgeStatus = s;
    statusEl.textContent = 'Bridge: ' + s;
    statusEl.className = 'status ' + (s === 'running' ? 'running' : 'stopped');
}

function addMessage(role, text) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.innerHTML = '<div class="bubble">' + escapeHtml(text) + '</div>';
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    const state = vscode.getState() || { messages: [] };
    state.messages.push({ role, text });
    vscode.setState(state);
}

function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}

async function sendMessage() {
    const input = document.getElementById('input') as HTMLTextAreaElement;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    addMessage('user', text);
    addMessage('assistant', '...');
    const lastBubble = document.querySelector('.msg:last-child .bubble');
    vscode.postMessage({ type: 'user', text });
}

async function restartBridge() {
    vscode.postMessage({ type: 'command', cmd: 'restart' });
}

async function clearChat() {
    document.getElementById('messages').innerHTML = '';
    vscode.setState({ messages: [] });
}

async function runSelection() {
    vscode.postMessage({ type: 'command', cmd: 'runSelection' });
}

window.addEventListener('message', msg => {
    const data = msg.data;
    if (data.type === 'status') updateStatus(data.status, data.info);
    if (data.type === 'thinking') {
        const bubbles = document.querySelectorAll('.msg.assistant');
        const last = bubbles[bubbles.length - 1];
        if (last) last.innerHTML = '<div class="bubble">' + escapeHtml(data.text) + '</div>';
    }
    if (data.type === 'assistant') {
        const bubbles = document.querySelectorAll('.msg.assistant');
        const last = bubbles[bubbles.length - 1];
        if (last) last.innerHTML = '<div class="bubble">' + escapeHtml(data.text) + '</div>';
        else addMessage('assistant', data.text);
    }
    if (data.type === 'error') {
        const bubbles = document.querySelectorAll('.msg.assistant');
        const last = bubbles[bubbles.length - 1];
        if (last) { last.className += ' error'; last.innerHTML = '<div class="bubble">' + escapeHtml(data.text) + '</div>'; }
        else addMessage('assistant', 'Error: ' + data.text);
    }
});

document.getElementById('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
</script>
</body>
</html>`;
    }
}

// ─── Task Runner View ───────────────────────────────────────────────

class TaskView {
    private bridgeManager: BridgeManager;

    constructor(bm: BridgeManager) {
        this.bridgeManager = bm;
    }

    async runTask(task: string): Promise<string> {
        const cfg = getConfig();
        const result = await bridgeRequest({
            model: cfg.model,
            input: [
                { role: 'system', content: 'You are Codex-Local autonomous agent. Execute the task and report results.' },
                { role: 'user', content: task },
            ],
            stream: false,
            max_output_tokens: cfg.maxTokens * 4,
        });
        return this.extractReply(result);
    }

    private extractReply(result: any): string {
        for (const output of (result.output || [])) {
            if (output.type === 'message') {
                for (const c of (output.content || [])) {
                    if (c.type === 'output_text') return c.text || '';
                }
            }
        }
        return 'No response';
    }
}

// ─── Extension Entry Point ──────────────────────────────────────────

let bridge: BridgeManager;
let inlineProvider: CodexInlineCompletionProvider;
let chatPanel: ChatPanel;
let taskView: TaskView;
let statusBar: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    bridge = new BridgeManager();
    inlineProvider = new CodexInlineCompletionProvider(bridge);
    chatPanel = new ChatPanel(bridge);
    taskView = new TaskView(bridge);

    // Status bar
    statusBar = vscode.window.createStatusBarItem(1, vscode.StatusBarAlignment.Right, 100);
    statusBar.text = '$(circle-slash) Codex-Local';
    statusBar.tooltip = 'Codex-Local';
    statusBar.command = 'codexLocal.status';
    statusBar.show();

    // Auto-start bridge if configured
    if (getConfig().autoStart) {
        bridge.start().catch(() => { });
    }

    // Register commands
    const cmds = [
        ['codexLocal.start', () => bridge.start().then(() => {
            vscode.window.showInformationMessage('Codex-Local bridge started');
        }).catch(e => vscode.window.showErrorMessage('Failed: ' + String(e)))],
        ['codexLocal.stop', () => { bridge.stop(); vscode.window.showInformationMessage('Bridge stopped'); }],
        ['codexLocal.status', showStatus],
        ['codexLocal.chat', () => chatPanel.show()],
        ['codexLocal.runTask', runTaskInteractive],
        ['codexLocal.restartBridge', restartBridgeServer],
    ] as const;

    for (const [cmd, fn] of cmds) {
        const disposable = vscode.commands.registerCommand(cmd, fn);
        context.subscriptions.push(disposable);
    }

    // Register inline completion
    const providerReg = vscode.languages.registerInlineCompletionItemProvider(
        { pattern: '**' },
        inlineProvider,
    );
    context.subscriptions.push(providerReg);

    // Status bar click
    statusBar.command = 'codexLocal.status';

    // Bridge status updates
    bridge.onStatus((s, info) => {
        statusBar.text = s === 'running'
            ? '$(check) Codex-Local'
            : '$(circle-slash) Codex-Local';
        statusBar.tooltip = `Bridge: ${s}`;
    });

    vscode.window.showInformationMessage('Codex-Local ready. Run CodexLocal.start or wait for auto-start.');
}

async function showStatus(): Promise<void> {
    const s = bridge.getStatus();
    if (s === 'running') {
        vscode.window.showInformationMessage('Bridge running on ' + getConfig().bridgeUrl);
    } else {
        const pick = await vscode.window.showQuickPick(['Start Bridge', 'Open Chat', 'Cancel']);
        if (pick === 'Start Bridge') bridge.start();
        else if (pick === 'Open Chat') chatPanel.show();
    }
}

async function restartBridgeServer(): Promise<void> {
    bridge.stop();
    await new Promise(r => setTimeout(r, 500));
    try {
        await bridge.start();
        vscode.window.showInformationMessage('Codex-Local bridge restarted');
    } catch (e: any) {
        vscode.window.showErrorMessage('Restart failed: ' + e.message);
    }
}

async function runTaskInteractive(): Promise<void> {
    const task = await vscode.window.showInputBox({
        prompt: 'Codex-Local Task',
        placeHolder: 'Describe the task to run...',
    });
    if (!task) return;

    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Codex-Local',
    }, async () => {
        const result = await taskView.runTask(task);
        const doc = await vscode.workspace.openTextDocument({ content: result, language: 'markdown' });
        await vscode.window.showTextDocument(doc, vscode.ViewColumn.Two);
    });
}

export function deactivate() {
    bridge?.stop();
}