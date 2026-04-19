<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import { getDouStudentAnnouncements, type DouAnnouncement } from '$lib/apis/douAcademic';

	let announcements: DouAnnouncement[] = [];
	let loading = true;
	let err: string | null = null;

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) { err = 'Giriş yapın.'; loading = false; return; }
		try {
			const r = await getDouStudentAnnouncements(token);
			announcements = r.announcements;
		} catch (e: unknown) { err = e instanceof Error ? e.message : 'API hatası.'; }
		loading = false;
	});
</script>

<svelte:head><title>OBS • Duyurular</title></svelte:head>

<ObsShell activePath="/obs/duyurular">
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	<div class="space-y-4">
		<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-sm font-semibold">Duyurular</div>
			<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
				<code class="rounded bg-slate-100 px-1 dark:bg-white/10">GET /api/v1/student/me/announcements</code>
			</div>
		</div>

		{#if loading}
			<div class="rounded-2xl border border-black/10 bg-white p-8 text-center text-sm text-slate-400 shadow-sm dark:border-white/10 dark:bg-white/5">Yükleniyor…</div>
		{:else if err}
			<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200">{err}</div>
		{:else if announcements.length}
			<div class="space-y-3">
				{#each announcements as ann}
					<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
						<div class="flex items-start justify-between gap-3">
							<div class="text-sm font-semibold">{ann.title}</div>
							<span class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-white/10 dark:text-slate-300">
								{ann.audience_type === 'all' ? 'Genel' : ann.audience_type === 'department' ? 'Bölüm' : ann.audience_type}
							</span>
						</div>
						<p class="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{ann.content}</p>
						<div class="mt-3 text-xs text-slate-400">
							{ann.published_at?.slice(0, 10) ?? ''} · {ann.created_by ?? ''}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-8 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">
				Henüz duyuru yok.
			</div>
		{/if}
	</div>
</ObsShell>
