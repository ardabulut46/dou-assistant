<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouAcademicSections,
		getDouDepartments,
		getDouTerms,
		type DouAcademicSectionsResponse,
		type DouDepartment,
		type DouTerm
	} from '$lib/apis/douAcademic';

	let terms: DouTerm[] = [];
	let departments: DouDepartment[] = [];
	let academic: DouAcademicSectionsResponse | null = null;
	let selectedTermId = 'term-2';
	let loading = true;
	let err: string | null = null;

	async function load() {
		if (!browser) return;
		loading = true;
		err = null;
		const token = localStorage.token ?? null;
		if (!token) {
			err = 'Bu sayfayı görmek için giriş yapın.';
			loading = false;
			return;
		}
		try {
			const [t, d, a] = await Promise.all([
				getDouTerms(token),
				getDouDepartments(token),
				getDouAcademicSections(token, selectedTermId)
			]);
			terms = t;
			departments = d;
			academic = a;
		} catch (e: unknown) {
			err = e instanceof Error ? e.message : 'API yüklenemedi.';
		} finally {
			loading = false;
		}
	}

	async function changeTerm(termId: string) {
		if (!browser) return;
		selectedTermId = termId;
		const token = localStorage.token ?? null;
		if (!token) return;
		try {
			academic = await getDouAcademicSections(token, termId);
		} catch {
			academic = null;
		}
	}

	onMount(load);
</script>

<svelte:head>
	<title>OBS • Dersler</title>
</svelte:head>

<ObsShell activePath="/obs/dersler">
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	<div class="space-y-4">
		<!-- Başlık + dönem seçici -->
		<div
			class="flex flex-col gap-3 rounded-2xl border border-black/10 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between dark:border-white/10 dark:bg-white/5"
		>
			<div>
				<div class="text-sm font-semibold">Ders ve Dönem (mock önizleme)</div>
				<div class="mt-0.5 text-xs text-slate-500 dark:text-slate-300">
					<code class="rounded bg-slate-100 px-1 dark:bg-white/10">/api/v1/terms</code>
					·
					<code class="rounded bg-slate-100 px-1 dark:bg-white/10">/api/v1/departments</code>
					·
					<code class="rounded bg-slate-100 px-1 dark:bg-white/10">/api/v1/academic/me/sections</code>
				</div>
			</div>

			{#if terms.length > 0}
				<select
					class="rounded-xl border border-black/10 bg-white px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
					bind:value={selectedTermId}
					on:change={() => changeTerm(selectedTermId)}
				>
					{#each terms as t}
						<option value={t.id}>{t.name}</option>
					{/each}
				</select>
			{/if}
		</div>

		{#if loading}
			<div class="rounded-2xl border border-black/10 bg-white p-8 text-center text-sm text-slate-400 shadow-sm dark:border-white/10 dark:bg-white/5">
				Yükleniyor…
			</div>
		{:else if err}
			<div
				class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-sm dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100"
			>
				{err}
			</div>
		{:else}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<!-- Dönemler -->
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Dönemler</div>
					<ul class="mt-3 space-y-2">
						{#each terms as t}
							<li
								class="flex items-center justify-between rounded-xl px-3 py-2 text-sm transition
								       {t.id === selectedTermId
									? 'bg-sky-50 font-semibold text-sky-700 dark:bg-sky-900/30 dark:text-sky-300'
									: 'text-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-white/5'}"
							>
								<span>{t.name}</span>
								<span class="text-xs text-slate-400">{t.academic_year}</span>
							</li>
						{/each}
					</ul>
				</div>

				<!-- Bölümler -->
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Bölümler</div>
					<ul class="mt-3 space-y-2">
						{#each departments as d}
							<li class="rounded-xl px-3 py-2 text-sm text-slate-700 dark:text-slate-300">
								<span class="mr-1 rounded bg-slate-100 px-1 font-mono text-xs dark:bg-white/10">{d.code}</span>
								{d.name}
							</li>
						{/each}
					</ul>
				</div>

				<!-- Akademisyen Şubeleri -->
				<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="text-xs font-semibold uppercase tracking-wide text-slate-500">
						Şubelerim
						{#if academic?.sections?.length}
							<span class="ml-1 rounded-full bg-sky-100 px-2 py-0.5 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
								{academic.sections.length}
							</span>
						{/if}
					</div>

					{#if !academic?.sections?.length}
						<div class="mt-4 text-sm text-slate-400">Bu dönem için şube bulunamadı.</div>
					{:else}
						<ul class="mt-3 space-y-3">
							{#each academic.sections as s}
								<li class="rounded-xl border border-black/5 p-3 dark:border-white/10">
									<div class="flex items-start justify-between gap-2">
										<div class="text-sm font-semibold text-slate-800 dark:text-slate-100">
											{s.course_code}
											<span class="ml-1 rounded bg-sky-100 px-1.5 py-0.5 text-xs font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
												{s.section_code}
											</span>
										</div>
										<div class="shrink-0 text-xs text-slate-400">
											{s.enrollment_count}/{s.capacity}
										</div>
									</div>
									<div class="mt-1 text-xs text-slate-500 dark:text-slate-400">
										{s.course_name}
									</div>
									<div class="mt-1 flex gap-3 text-xs text-slate-400">
										<span>{s.day_of_week} {s.start_time}–{s.end_time}</span>
										<span>· {s.classroom}</span>
									</div>
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			</div>

			<!-- Mock uyarısı -->
			{#if academic?._mock}
				<div class="rounded-xl border border-amber-200/60 bg-amber-50/60 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300">
					Mock veri — PostgreSQL tabloları henüz oluşturulmadı (Faz 2 migration bekleniyor).
				</div>
			{/if}
		{/if}
	</div>
</ObsShell>
