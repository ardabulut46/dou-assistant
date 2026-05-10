import { browser } from '$app/environment';
// import { version } from '../../package.json';

export const APP_NAME = 'DouGPT';

/**
 * API kökü. OBS `fetch` için **`getWebuiApiBaseUrl()`** kullanın (çağrı anında çözülür).
 *
 * Production (aynı host): boş → göreli `/api/v1`.
 * `.env`: `VITE_OPEN_WEBUI_BACKEND_URL`.
 */
export function getWebuiBackendOrigin(): string {
	if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_OPEN_WEBUI_BACKEND_URL) {
		const v = String(import.meta.env.VITE_OPEN_WEBUI_BACKEND_URL).trim();
		if (v) return v.replace(/\/$/, '');
	}
	if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
		return 'http://127.0.0.1:8080';
	}
	if (typeof window !== 'undefined' && window.location) {
		const { hostname: rawHost, port, protocol } = window.location;
		if (!port || port === '8080') return '';
		const hostname = rawHost.replace(/^\[|\]$/g, '');
		const looksLocal =
			hostname === 'localhost' ||
			hostname === '127.0.0.1' ||
			hostname === '::1' ||
			hostname === '0:0:0:0:0:0:0:1';
		const looksLan =
			/^192\.168\.\d{1,3}\.\d{1,3}$/.test(hostname) ||
			/^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname);
		if (!looksLocal && !looksLan) return '';
		let apiHost = hostname;
		if (looksLocal) {
			apiHost = '127.0.0.1';
		}
		const hostPart =
			apiHost.includes(':') && !apiHost.includes('.') ? `[${apiHost}]` : apiHost;
		return `${protocol}//${hostPart}:8080`;
	}
	return '';
}

export function getWebuiApiBaseUrl(): string {
	const o = getWebuiBackendOrigin();
	return o ? `${o.replace(/\/$/, '')}/api/v1` : '/api/v1';
}

export const WEBUI_HOSTNAME = browser ? location.host : '';
export const WEBUI_BASE_URL = browser ? '' : '';
/** SSR'da '' olabilir; img URL vb. API için `getWebuiApiBaseUrl` kullanın. */
export const WEBUI_BACKEND_ORIGIN = browser ? getWebuiBackendOrigin() : '';

export const WEBUI_API_BASE_URL = `${WEBUI_BACKEND_ORIGIN}/api/v1`;

export const OLLAMA_API_BASE_URL = `${WEBUI_BACKEND_ORIGIN}/ollama`;
export const OPENAI_API_BASE_URL = `${WEBUI_BACKEND_ORIGIN}/openai`;
export const AUDIO_API_BASE_URL = `${WEBUI_BACKEND_ORIGIN}/api/v1/audio`;
export const IMAGES_API_BASE_URL = `${WEBUI_BACKEND_ORIGIN}/api/v1/images`;
export const RETRIEVAL_API_BASE_URL = `${WEBUI_BACKEND_ORIGIN}/api/v1/retrieval`;

export const WEBUI_VERSION = APP_VERSION;
export const WEBUI_BUILD_HASH = APP_BUILD_HASH;
export const REQUIRED_OLLAMA_VERSION = '0.1.16';

export const SUPPORTED_FILE_TYPE = [
	'application/epub+zip',
	'application/pdf',
	'text/plain',
	'text/csv',
	'text/xml',
	'text/html',
	'text/x-python',
	'text/css',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'application/octet-stream',
	'application/x-javascript',
	'text/markdown',
	'audio/mpeg',
	'audio/wav',
	'audio/ogg',
	'audio/x-m4a'
];

export const SUPPORTED_FILE_EXTENSIONS = [
	'md',
	'rst',
	'go',
	'py',
	'java',
	'sh',
	'bat',
	'ps1',
	'cmd',
	'js',
	'ts',
	'css',
	'cpp',
	'hpp',
	'h',
	'c',
	'cs',
	'htm',
	'html',
	'sql',
	'log',
	'ini',
	'pl',
	'pm',
	'r',
	'dart',
	'dockerfile',
	'env',
	'php',
	'hs',
	'hsc',
	'lua',
	'nginxconf',
	'conf',
	'm',
	'mm',
	'plsql',
	'perl',
	'rb',
	'rs',
	'db2',
	'scala',
	'bash',
	'swift',
	'vue',
	'svelte',
	'doc',
	'docx',
	'pdf',
	'csv',
	'txt',
	'xls',
	'xlsx',
	'pptx',
	'ppt',
	'msg'
];

export const DEFAULT_CAPABILITIES = {
	file_context: true,
	vision: true,
	file_upload: true,
	web_search: true,
	image_generation: true,
	code_interpreter: true,
	citations: true,
	status_updates: true,
	usage: undefined,
	builtin_tools: true
};

export const PASTED_TEXT_CHARACTER_LIMIT = 1000;

// Source: https://kit.svelte.dev/docs/modules#$env-static-public
// This feature, akin to $env/static/private, exclusively incorporates environment variables
// that are prefixed with config.kit.env.publicPrefix (usually set to PUBLIC_).
// Consequently, these variables can be securely exposed to client-side code.
