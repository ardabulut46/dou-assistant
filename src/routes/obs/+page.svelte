<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { user } from '$lib/stores';
	import { obsAreaHome, resolveObsAreaWithDevOverride } from '$lib/obs/obsAccess';

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		const area = await resolveObsAreaWithDevOverride(token, $user?.role ?? null);
		goto(obsAreaHome(area), { replaceState: true });
	});
</script>

<div class="flex min-h-screen items-center justify-center bg-slate-100 dark:bg-slate-950">
	<div class="text-sm text-slate-400">Yönlendiriliyor…</div>
</div>
