<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouAcademicSections,
		getDouTerms,
		type DouSection,
		type DouTerm
	} from '$lib/apis/douAcademic';

	let terms: DouTerm[] = [];
	let sections: DouSection[] = [];
	let selectedTermId = '';
	let loading = true;
	let err: string | null = null;

	async function load(termId?: string) {
		if (!browser) return;
		loading = true; err = null;
		const token = localStorage.token ?? null;
		if (!token) { err = 'Giriş yapın.'; loading = false; return; }
		try {
			if (!terms.length) terms = await getDouTerms(token);
			if (!selectedTermId) selectedTermId = terms.find(t => t.is_active)?.id ?? terms[0]?.id ?? '';
			const r = await getDouAcademicSections(token, termId || selectedTermId);
			sections = r.sections;
		} catch (e: unknown) { err = e instanceof Error ? e.message : 'API hatası.'; }
		loading = false;
	}

	onMount(() => load());
</script>

<svelte:head><title>OBS • Açılan Bölüm Dersleri</title></svelte:head>

<ObsShell activePath="/obs/dersler/acilan">
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	<div class="space-y-4">
		<div class="flex flex-col gap-3 rounded-2xl border border-black/10 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between dark:border-white/10 dark:bg-white/5">
			<div>
				<div class="text-sm font-semibold">Açılan Bölüm Dersleri</div>
				<div class="mt-0.5 text-xs text-slate-500 dark:text-slate-300">
					<code class="rounded bg-slate-100 px-1 dark:bg-white/10">GET /api/v1/academic/me/sections</code>
				</div>
			</div>
			{#if terms.length}
				<select
					class="rounded-xl border border-black/10 bg-white px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
					bind:value={selectedTermId}
					on:change={() => load(selectedTermId)}
				>
					{#each terms as t}<option value={t.id}>{t.name}</option>{/each}
				</select>
			{/if}
		</div>

		{#if loading}
			<div class="rounded-2xl border border-black/10 bg-white p-8 text-center text-sm text-slate-400 shadow-sm dark:border-white/10 dark:bg-white/5">Yükleniyor…</div>
		{:else if err}
			<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200">{err}</div>
		{:else if sections.length}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-center">Şb.</th>
								<th class="px-4 py-3 text-left">Kod</th>
								<th class="px-4 py-3 text-left">Ders Adı</th>
								<th class="px-4 py-3 text-left">Öğretim Elemanı</th>
								<th class="px-4 py-3 text-left">Gün / Saat</th>
								<th class="px-4 py-3 text-left">Derslik</th>
								<th class="px-4 py-3 text-center">Kontenjan</th>
							</tr>
						</thead>
						<tbody>
							{#each sections as s}
								<tr class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 dark:hover:bg-white/5">
									<td class="px-4 py-3 text-center font-semibold">{s.section_no}</td>
									<td class="px-4 py-3 font-mono text-xs font-semibold">{s.course_code}</td>
									<td class="px-4 py-3">{s.course_name}</td>
									<td class="px-4 py-3 text-xs text-slate-500">{s.instructor_name ?? '—'}</td>
									<td class="px-4 py-3 text-xs">{s.day_of_week} {s.start_time}–{s.end_time}</td>
									<td class="px-4 py-3 text-xs">{s.classroom}</td>
									<td class="px-4 py-3 text-center text-xs">
										<span class="{s.enrollment_count >= s.capacity ? 'text-red-600 dark:text-red-400' : 'text-slate-600 dark:text-slate-300'}">{s.enrollment_count}/{s.capacity}</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{:else}
			<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Bu dönemde açılan ders bulunamadı.</div>
		{/if}
	</div>
</ObsShell>
