<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { getDouTerms, type DouTerm } from '$lib/apis/douAcademic';
	import { ogrenciLayoutSubtitle } from '$lib/obs/ogrenci/paths';
	import { obsAreaHome, resolveObsAreaWithDevOverride, type ObsArea } from '$lib/obs/obsAccess';
	import { user } from '$lib/stores';

	let activeTerm: DouTerm | null = null;
	let allowed = false;

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) {
			goto('/auth');
			return;
		}
		const area: ObsArea = await resolveObsAreaWithDevOverride(token, $user?.role ?? null);
		if (area !== 'ogrenci') {
			goto(obsAreaHome(area), { replaceState: true });
			return;
		}
		allowed = true;
		try {
			const terms = await getDouTerms(token);
			activeTerm = terms.find((t) => t.is_active) ?? terms[terms.length - 1] ?? null;
		} catch {
			activeTerm = null;
		}
	});

	$: subTitle = ogrenciLayoutSubtitle($page.url.pathname);
</script>

{#if allowed}
	<ObsShell activePath={$page.url.pathname} role="ogrenci" termLabel={activeTerm?.name ?? '—'}>
		<span slot="userline">{$user?.name ?? 'Öğrenci'} • {subTitle}</span>
		<slot />
	</ObsShell>
{:else}
	<div
		class="flex min-h-[50vh] items-center justify-center bg-slate-100 text-sm text-slate-500 dark:bg-slate-950"
	>
		Erişim kontrol ediliyor…
	</div>
{/if}
