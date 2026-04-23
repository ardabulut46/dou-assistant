import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

import { viteStaticCopy } from 'vite-plugin-static-copy';

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, process.cwd(), '');
	const backend = env.VITE_OPEN_WEBUI_BACKEND_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8080';

	return {
		plugins: [
			sveltekit(),
			viteStaticCopy({
				targets: [
					{
						src: 'node_modules/onnxruntime-web/dist/*.jsep.*',

						dest: 'wasm'
					}
				]
			})
		],
		define: {
			APP_VERSION: JSON.stringify(process.env.npm_package_version),
			APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'dev-build')
		},
		build: {
			sourcemap: true
		},
		worker: {
			format: 'es'
		},
		esbuild: {
			pure: process.env.ENV === 'dev' ? [] : ['console.log', 'console.debug', 'console.error']
		},
		server: {
			proxy: {
				'/api': { target: backend, changeOrigin: true },
				'/static': { target: backend, changeOrigin: true },
				'/ws': { target: backend, changeOrigin: true, ws: true },
				'/ollama': { target: backend, changeOrigin: true },
				'/openai': { target: backend, changeOrigin: true },
				'/oauth': { target: backend, changeOrigin: true },
				'/user.png': { target: backend, changeOrigin: true }
			}
		}
	};
});
