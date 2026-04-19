<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouStudentGrades,
		getDouTerms,
		type DouGradeEntry,
		type DouTerm
	} from '$lib/apis/douAcademic';

	let terms: DouTerm[] = [];
	let grades: DouGradeEntry[] = [];
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
			const r = await getDouStudentGrades(token, termId || selectedTermId);
			grades = r.grades;
		} catch (e: unknown) { err = e instanceof Error ? e.message : 'API hatası.'; }
		loading = false;
	}

	onMount(() => load());
</script>

<svelte:head><title>OBS • Not Listesi</title></svelte:head>

<ObsShell activePath="/obs/notlar">
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	<div class="space-y-4">
		<div class="flex flex-col gap-3 rounded-2xl border border-black/10 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between dark:border-white/10 dark:bg-white/5">
			<div>
				<div class="text-sm font-semibold">Not Listesi</div>
				<div class="mt-0.5 text-xs text-slate-500 dark:text-slate-300">
					<code class="rounded bg-slate-100 px-1 dark:bg-white/10">GET /api/v1/student/me/grades</code>
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
		{:else}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Ders Kodu</th>
								<th class="px-4 py-3 text-left">Ders Adı</th>
								<th class="px-4 py-3 text-center">Vize</th>
								<th class="px-4 py-3 text-center">Final</th>
								<th class="px-4 py-3 text-center">Harf</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each grades as g}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3 font-mono text-xs font-semibold">{g.course_code}</td>
									<td class="px-4 py-3 text-xs text-slate-600 dark:text-slate-300">{g.course_name}</td>
									<td class="px-4 py-3 text-center">{g.midterm ?? '—'}</td>
									<td class="px-4 py-3 text-center">{g.final ?? '—'}</td>
									<td class="px-4 py-3 text-center font-bold">
										{#if g.is_published && g.letter_grade}
											<span class="rounded-full bg-emerald-100 px-2.5 py-0.5 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{g.letter_grade}</span>
										{:else}—{/if}
									</td>
									<td class="px-4 py-3 text-center text-xs">
										{#if g.is_published}
											<span class="text-emerald-600 dark:text-emerald-400">Yayınlandı</span>
										{:else if g.is_finalized}
											<span class="text-amber-600 dark:text-amber-400">Kesinleşti</span>
										{:else if g.midterm == null && g.final == null}
											<span class="text-slate-400">Not girilmedi</span>
										{:else}
											<span class="text-sky-600 dark:text-sky-400">Taslak</span>
										{/if}
									</td>
								</tr>
							{:else}
								<tr><td colspan="6" class="px-4 py-8 text-center text-slate-400">Bu dönem için not bulunamadı.</td></tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}
	</div>
</ObsShell>
