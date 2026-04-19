<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import { getDouStudentProfile, type DouStudentProfile } from '$lib/apis/douAcademic';

	let profile: DouStudentProfile | null = null;
	let loading = true;
	let err: string | null = null;

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) { err = 'Giriş yapın.'; loading = false; return; }
		try { profile = await getDouStudentProfile(token); }
		catch (e: unknown) { err = e instanceof Error ? e.message : 'API hatası.'; }
		loading = false;
	});

	const fields: [string, (p: DouStudentProfile) => string][] = [
		['Öğrenci No',   p => p.student_no],
		['Ad Soyad',     p => p.full_name ?? '—'],
		['E-posta',      p => p.email],
		['Bölüm',        p => p.department_name],
		['Fakülte',      p => p.faculty_name ?? '—'],
		['Program',      p => p.program],
		['Sınıf',        p => `${p.class_level}. sınıf`],
		['GNO',          p => p.gpa != null ? p.gpa.toFixed(2) : '—'],
		['Durum',        p => p.status ?? '—'],
		['Kayıt Tarihi', p => p.enrollment_date ?? '—'],
		['Mali Durum',   p => p.is_financially_eligible ? 'Uygun ✓' : 'Borçlu ✗'],
	];
</script>

<svelte:head><title>OBS • Özlük Bilgileri</title></svelte:head>

<ObsShell activePath="/obs/ozluk/genel">
	<span slot="userline">{$user?.name ?? 'Kullanıcı'} • OBS</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">Özlük Bilgileri</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			<code class="rounded bg-slate-100 px-1 dark:bg-white/10">GET /api/v1/student/me/profile</code>
		</div>

		{#if loading}
			<div class="mt-6 text-center text-sm text-slate-400">Yükleniyor…</div>
		{:else if err}
			<div class="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200">{err}</div>
		{:else if profile}
			<div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
				{#each fields as [label, fn]}
					<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
						<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</div>
						<div class="mt-1 text-sm font-medium">{fn(profile)}</div>
					</div>
				{/each}
			</div>
			{#if profile._mock}
				<div class="mt-4 rounded-xl border border-amber-200/60 bg-amber-50/60 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300">
					Mock veri — PostgreSQL migration'ları tamamlandığında gerçek verilerle değiştirilecek.
				</div>
			{/if}
		{/if}
	</div>
</ObsShell>
