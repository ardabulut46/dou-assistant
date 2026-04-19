<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouStudentProfile,
		getDouStudentAdvisor,
		getDouTerms,
		type DouStudentProfile,
		type DouAdvisorResponse,
		type DouTerm
	} from '$lib/apis/douAcademic';

	let profile: DouStudentProfile | null = null;
	let advisor: DouAdvisorResponse | null = null;
	let activeTerm: DouTerm | null = null;
	let loading = true;

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) { loading = false; return; }

		const [pRes, aRes, tRes] = await Promise.allSettled([
			getDouStudentProfile(token),
			getDouStudentAdvisor(token),
			getDouTerms(token)
		]);

		if (pRes.status === 'fulfilled') profile = pRes.value;
		if (aRes.status === 'fulfilled') advisor = aRes.value;
		if (tRes.status === 'fulfilled') {
			const terms = tRes.value;
			activeTerm = terms.find(t => t.is_active) ?? terms[terms.length - 1] ?? null;
		}

		loading = false;
	});
</script>

<svelte:head><title>OBS — Öğrenci Bilgi Sistemi</title></svelte:head>

<ObsShell activePath="/obs" termLabel={activeTerm?.name ?? '2025-2026 Bahar'}>
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	{#if !loading && profile}
		<div class="mb-5 flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm dark:border-emerald-900/30 dark:bg-emerald-950/30">
			<span class="text-emerald-600 dark:text-emerald-400">●</span>
			<span>
				<strong>{activeTerm?.name ?? '—'}</strong> döneminde kayıtlısınız.
				AKTS limitiniz: <strong>{profile.gpa != null && profile.gpa >= 2.50 ? 36 : 30}</strong>
				{#if profile.is_financially_eligible}
					· <span class="text-emerald-700 dark:text-emerald-300">Mali durum: Uygun ✓</span>
				{:else}
					· <span class="text-red-600 dark:text-red-400">Harç borcu var ✗</span>
				{/if}
			</span>
		</div>
	{/if}

	<!-- Özet kartlar -->
	<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500">Aktif Dönem</div>
			<div class="mt-1 text-sm font-semibold">{activeTerm?.name ?? (loading ? '…' : '—')}</div>
			{#if activeTerm}
				<div class="mt-2"><span class="rounded-xl bg-sky-100 px-2 py-0.5 text-xs text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">Aktif</span></div>
			{/if}
		</div>

		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500">Danışman</div>
			<div class="mt-1 text-sm font-semibold">{advisor?.advisor?.name ?? (loading ? '…' : '—')}</div>
			{#if advisor?.advisor?.email}
				<div class="mt-1 text-xs text-slate-400">{advisor.advisor.email}</div>
			{/if}
		</div>

		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500">Öğrenci No / Bölüm</div>
			<div class="mt-1 text-sm font-semibold">{profile?.student_no ?? (loading ? '…' : '—')}</div>
			{#if profile}
				<div class="mt-1 text-xs text-slate-400">{profile.department_name}</div>
			{/if}
		</div>

		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500">GNO / Sınıf</div>
			<div class="mt-1 text-sm font-semibold">{profile?.gpa?.toFixed(2) ?? (loading ? '…' : '—')}</div>
			{#if profile}
				<div class="mt-1 text-xs text-slate-400">{profile.class_level}. Sınıf</div>
			{/if}
		</div>
	</div>

	<!-- Hızlı erişim -->
	<div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
		{#each [
			['/obs/genel/alinan-dersler',        'Alınan Dersler',         'Kayıtlı ders listesi ve dönem bilgileri'],
			['/obs/ders-donem/not-listesi',       'Not Listesi',            'Vize, final ve harf notları'],
			['/obs/genel/sinav-takvimi',          'Sınav Takvimi',          'Yaklaşan sınav tarihleri'],
			['/obs/genel/ders-programi',          'Ders Programı',          'Haftalık ders çizelgesi'],
			['/obs/ders-donem/devamsizlik-durumu','Devamsızlık',            'Devam durumu ve oranlar'],
			['/obs/kullanici/gelen-mesajlar',     'Mesajlar',               'Danışman ve sistem mesajları'],
			['/obs/genel/genel-duyurular',        'Duyurular',              'Bölüm ve genel duyurular'],
			['/obs/kullanici/belge-talebi',       'Belge Talebi',           'Transkript, öğrenci belgesi'],
			['/obs/ders-donem/transkript',        'Transkript',             'Tüm dönemler, genel ortalama'],
		] as [href, cardTitle, desc]}
			<a {href} class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm transition hover:-translate-y-[1px] hover:bg-slate-50 hover:shadow dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10">
				<div class="text-sm font-semibold">{cardTitle}</div>
				<div class="mt-1 text-xs text-slate-500 dark:text-slate-400">{desc}</div>
			</a>
		{/each}
	</div>

	{#if profile?._mock}
		<div class="mt-4 rounded-xl border border-amber-200/60 bg-amber-50/60 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300">
			Mock veri — PostgreSQL migration'ları tamamlandığında gerçek verilerle değiştirilecek.
		</div>
	{/if}
</ObsShell>
