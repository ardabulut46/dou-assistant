<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouStudentEnrollments,
		getDouTerms,
		type DouEnrollment,
		type DouTerm
	} from '$lib/apis/douAcademic';

	let terms: DouTerm[] = [];
	let enrollments: DouEnrollment[] = [];
	let totalAkts = 0;
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
			const r = await getDouStudentEnrollments(token, termId || selectedTermId);
			enrollments = r.enrollments;
			totalAkts   = r.total_akts ?? 0;
		} catch (e: unknown) { err = e instanceof Error ? e.message : 'API hatası.'; }
		loading = false;
	}

	onMount(() => load());
</script>

<svelte:head><title>OBS • Alınan Dersler</title></svelte:head>

<ObsShell activePath="/obs/dersler/alinan">
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	<div class="space-y-4">
		<!-- Başlık + dönem seçici -->
		<div class="flex flex-col gap-3 rounded-2xl border border-black/10 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between dark:border-white/10 dark:bg-white/5">
			<div>
				<div class="text-sm font-semibold">Alınan Dersler</div>
				<div class="mt-0.5 text-xs text-slate-500 dark:text-slate-300">
					<code class="rounded bg-slate-100 px-1 dark:bg-white/10">GET /api/v1/student/me/enrollments</code>
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
		{:else if enrollments.length}
			<div class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="flex items-center justify-between px-5 py-3 text-xs text-slate-500">
					<span>{enrollments.length} ders</span>
					<span>Toplam AKTS: <strong class="text-slate-800 dark:text-slate-100">{totalAkts}</strong></span>
				</div>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-xs text-slate-600 dark:bg-white/5 dark:text-slate-300">
							<tr>
								<th class="px-4 py-3 text-left">Kod</th>
								<th class="px-4 py-3 text-left">Ders Adı</th>
								<th class="px-4 py-3 text-center">K</th>
								<th class="px-4 py-3 text-center">AKTS</th>
								<th class="px-4 py-3 text-center">T+U</th>
								<th class="px-4 py-3 text-left">Öğr. Elemanı</th>
								<th class="px-4 py-3 text-left">Gün / Saat</th>
								<th class="px-4 py-3 text-left">Derslik</th>
								<th class="px-4 py-3 text-center">Z/S</th>
							</tr>
						</thead>
						<tbody>
							{#each enrollments as e}
								<tr class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 dark:hover:bg-white/5">
									<td class="px-4 py-3 font-mono text-xs font-semibold">{e.course_code}</td>
									<td class="px-4 py-3">{e.course_name}</td>
									<td class="px-4 py-3 text-center">{e.credits}</td>
									<td class="px-4 py-3 text-center">{e.akts}</td>
									<td class="px-4 py-3 text-center text-xs">{e.theory_hours ?? '—'}</td>
									<td class="px-4 py-3 text-xs text-slate-500">{e.instructor_name ?? '—'}</td>
									<td class="px-4 py-3 text-xs">{e.day_of_week ?? '—'} {e.start_time}–{e.end_time}</td>
									<td class="px-4 py-3 text-xs">{e.classroom ?? '—'}</td>
									<td class="px-4 py-3 text-center">
										<span class="rounded px-1.5 py-0.5 text-xs {e.type === 'Z' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'}">{e.type ?? '—'}</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{:else}
			<div class="rounded-2xl border border-dashed border-black/15 bg-slate-50 p-6 text-center text-sm text-slate-400 dark:border-white/15 dark:bg-white/5">Bu dönemde kayıtlı ders bulunamadı.</div>
		{/if}
	</div>
</ObsShell>
