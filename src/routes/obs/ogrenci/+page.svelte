<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
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

	const quickLinks = [
		{ href: '/obs/ogrenci/alinan-dersler',      title: 'Alınan Dersler',      desc: 'Dönem ders listesi',            icon: '📚' },
		{ href: '/obs/ogrenci/not-listesi',          title: 'Not Listesi',         desc: 'Vize, final ve harf notları',   icon: '📊' },
		{ href: '/obs/ogrenci/sinav-takvimi',        title: 'Sınav Takvimi',       desc: 'Yaklaşan sınavlar',            icon: '📅' },
		{ href: '/obs/ogrenci/ders-programi',        title: 'Ders Programı',       desc: 'Haftalık çizelge',             icon: '🗓️' },
		{ href: '/obs/ogrenci/devamsizlik-durumu',   title: 'Devamsızlık',         desc: 'Devam oranları',                icon: '✅' },
		{ href: '/obs/ogrenci/mesajlar-gelen',       title: 'Mesajlar',            desc: 'Gelen kutusu',                  icon: '✉️' },
		{ href: '/obs/ogrenci/duyurular',            title: 'Duyurular',           desc: 'Bölüm ve genel duyurular',      icon: '📢' },
		{ href: '/obs/ogrenci/belge-talebi',         title: 'Belge Talebi',        desc: 'Transkript, öğrenci belgesi',   icon: '📄' },
		{ href: '/obs/ogrenci/transkript',           title: 'Transkript',          desc: 'Tüm dönemler',                  icon: '🎓' },
	];
</script>

<svelte:head><title>OBS — Öğrenci Paneli</title></svelte:head>

<div class="space-y-4">
	<!-- Durum bandı -->
	{#if !loading && profile}
		<div class="mb-5 flex items-center gap-3 rounded-xl border px-5 py-3 text-sm
			{profile.is_financially_eligible
				? 'border-emerald-200 bg-emerald-50 dark:border-emerald-900/30 dark:bg-emerald-950/20'
				: 'border-red-200 bg-red-50 dark:border-red-900/30 dark:bg-red-950/20'}">
			<span class="{profile.is_financially_eligible ? 'text-emerald-500' : 'text-red-500'}">●</span>
			<span class="text-slate-700 dark:text-slate-200">
				<strong class="font-semibold">{activeTerm?.name ?? '—'}</strong> dönemi aktif.
				AKTS limiti: <strong>{profile.gpa != null && profile.gpa >= 2.50 ? 36 : 30}</strong>
				{#if profile.is_financially_eligible}
					· <span class="font-medium text-emerald-700 dark:text-emerald-300">Mali durum: Uygun</span>
				{:else}
					· <span class="font-medium text-red-700 dark:text-red-400">Harç borcu mevcut</span>
				{/if}
			</span>
		</div>
	{/if}

	<!-- Özet kartlar -->
	<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
		{#each [
			{ label: 'Aktif Dönem',    value: activeTerm?.name ?? (loading ? '…' : '—'),   sub: activeTerm ? 'Aktif' : '' },
			{ label: 'Danışman',       value: advisor?.advisor?.name ?? (loading ? '…' : '—'), sub: advisor?.advisor?.title ?? '' },
			{ label: 'Öğrenci No',     value: profile?.student_no ?? (loading ? '…' : '—'),    sub: profile?.department_name ?? '' },
			{ label: 'GNO / Sınıf',   value: profile?.gpa?.toFixed(2) ?? (loading ? '…' : '—'), sub: profile ? `${profile.class_level}. Sınıf` : '' },
		] as card}
			<div class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">{card.label}</div>
				<div class="mt-1.5 text-sm font-bold text-slate-900 dark:text-slate-100 truncate">{card.value}</div>
				{#if card.sub}
					<div class="mt-1 truncate text-xs text-slate-400">{card.sub}</div>
				{/if}
			</div>
		{/each}
	</div>

	<!-- Hızlı erişim -->
	<div class="mt-5">
		<div class="mb-3 text-xs font-bold tracking-widest text-slate-400 dark:text-slate-500">HIZLI ERİŞİM</div>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each quickLinks as lnk}
				<a
					href={lnk.href}
					class="group flex items-start gap-3 rounded-xl border border-black/10 bg-white p-4 shadow-sm transition hover:-translate-y-px hover:shadow-md dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/8"
				>
					<span class="text-xl leading-none">{lnk.icon}</span>
					<div class="min-w-0">
						<div class="text-sm font-semibold text-slate-800 group-hover:text-sky-600 dark:text-slate-100 dark:group-hover:text-sky-400 transition-colors">{lnk.title}</div>
						<div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{lnk.desc}</div>
					</div>
				</a>
			{/each}
		</div>
	</div>

</div>
