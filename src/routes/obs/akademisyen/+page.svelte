<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouAcademicSections,
		getDouAcademicApprovalRequests,
		getDouTerms,
		type DouSection,
		type DouTerm
	} from '$lib/apis/douAcademic';

	let sections: DouSection[] = [];
	let pendingApprovals = 0;
	let activeTerm: DouTerm | null = null;
	let loading = true;

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) {
			loading = false;
			return;
		}

		const [sRes, aRes, tRes] = await Promise.allSettled([
			getDouAcademicSections(token),
			getDouAcademicApprovalRequests(token, 'pending'),
			getDouTerms(token)
		]);

		if (sRes.status === 'fulfilled') sections = sRes.value.sections ?? [];
		if (aRes.status === 'fulfilled') pendingApprovals = aRes.value.total ?? 0;
		if (tRes.status === 'fulfilled') {
			const terms = tRes.value as DouTerm[];
			activeTerm = terms.find((t) => t.is_active) ?? terms[terms.length - 1] ?? null;
		}
		loading = false;
	});

	const quickLinks = [
		{
			href: '/obs/akademisyen/subelerim',
			title: 'Şubelerim',
			desc: 'Verdiğim dersler',
			icon: '📚'
		},
		{
			href: '/obs/akademisyen/not-girisi',
			title: 'Not Girişi',
			desc: 'Öğrenci notlarını gir',
			icon: '📝'
		},
		{
			href: '/obs/akademisyen/yoklama-girisi',
			title: 'Yoklama Girişi',
			desc: 'Haftalık yoklama',
			icon: '✅'
		},
		{
			href: '/obs/akademisyen/danismanlik-ogrencilerim',
			title: 'Danışmanlık',
			desc: 'Öğrenci listesi',
			icon: '🎓'
		},
		{
			href: '/obs/akademisyen/onay-talepleri',
			title: 'Onay Talepleri',
			desc: `${pendingApprovals} bekliyor`,
			icon: '⏳'
		},
		{ href: '/obs/akademisyen/mesajlar-gelen', title: 'Mesajlar', desc: 'Gelen kutusu', icon: '✉️' }
	];
</script>

<svelte:head><title>OBS — Akademisyen Paneli</title></svelte:head>

<ObsShell
	activePath="/obs/akademisyen"
	role="akademisyen"
	termLabel={activeTerm?.name ?? '2025-2026 Bahar'}
>
	<span slot="userline">{$user?.name ?? 'Akademisyen'} • Akademisyen Paneli</span>

	<!-- Özet kartlar -->
	<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
		{#each [{ label: 'Aktif Dönem', value: activeTerm?.name ?? (loading ? '…' : '—'), badge: activeTerm ? 'Aktif' : '' }, { label: 'Şube Sayısı', value: sections.length.toString(), badge: '' }, { label: 'Bekleyen Onay', value: pendingApprovals.toString(), badge: pendingApprovals > 0 ? 'Var' : '' }, { label: 'Ünvan', value: $user?.name ?? '—', badge: '' }] as card}
			<div
				class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">{card.label}</div>
				<div class="mt-1.5 truncate text-sm font-bold text-slate-900 dark:text-slate-100">
					{card.value}
				</div>
				{#if card.badge}
					<span
						class="mt-1 inline-block rounded-full {card.badge === 'Var'
							? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
							: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300'} px-2 py-0.5 text-[10px] font-bold"
						>{card.badge}</span
					>
				{/if}
			</div>
		{/each}
	</div>

	<!-- Şubeler özet -->
	{#if sections.length}
		<div
			class="mt-5 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
		>
			<div class="px-5 py-3 text-xs font-bold tracking-widest text-slate-400 dark:text-slate-500">
				AKTİF ŞUBELERİM
			</div>
			{#each sections.slice(0, 5) as s}
				<a
					href="/obs/akademisyen/subelerim"
					class="flex items-center justify-between border-t border-black/5 px-5 py-3 text-sm hover:bg-slate-50 transition-colors dark:border-white/10 dark:hover:bg-white/5"
				>
					<div>
						<span class="font-mono text-xs font-semibold text-slate-500">{s.course_code}</span>
						<span class="ml-2 font-medium">{s.course_name}</span>
					</div>
					<span class="text-xs text-slate-400">{s.day_of_week ?? ''} {s.start_time ?? ''}</span>
				</a>
			{/each}
		</div>
	{/if}

	<!-- Hızlı erişim -->
	<div class="mt-5">
		<div class="mb-3 text-xs font-bold tracking-widest text-slate-400 dark:text-slate-500">
			HIZLI ERİŞİM
		</div>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each quickLinks as lnk}
				<a
					href={lnk.href}
					class="group flex items-start gap-3 rounded-xl border border-black/10 bg-white p-4 shadow-sm transition hover:-translate-y-px hover:shadow-md dark:border-white/10 dark:bg-white/5"
				>
					<span class="text-xl leading-none">{lnk.icon}</span>
					<div class="min-w-0">
						<div
							class="text-sm font-semibold group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors"
						>
							{lnk.title}
						</div>
						<div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{lnk.desc}</div>
					</div>
				</a>
			{/each}
		</div>
	</div>
</ObsShell>
