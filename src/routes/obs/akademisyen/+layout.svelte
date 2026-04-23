<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { user } from '$lib/stores';
	import { obsAreaHome, resolveObsAreaWithDevOverride, type ObsArea } from '$lib/obs/obsAccess';

	let allowed = false;

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) {
			goto('/auth');
			return;
		}
		const area: ObsArea = await resolveObsAreaWithDevOverride(token, $user?.role ?? null);
		if (area !== 'akademisyen') {
			goto(obsAreaHome(area), { replaceState: true });
			return;
		}
		allowed = true;
	});
</script>

{#if allowed}
	<slot />
{:else}
	<div class="flex min-h-[50vh] items-center justify-center bg-slate-100 text-sm text-slate-500 dark:bg-slate-950">
		Erişim kontrol ediliyor…
	</div>
{/if}
