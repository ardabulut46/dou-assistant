<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { devSeedUsers, devGetObsRole, type DevAccount } from '$lib/apis/douAcademic';

	let accounts: DevAccount[] = [];
	let loading  = true;
	let seeding  = false;
	let err: string | null = null;
	let currentRole = '';
	let currentEmail = '';

	const ROLE_ICONS: Record<string, string> = {
		ogrenci:     '🎓',
		Akademisyen: '👨‍🏫',
		Admin:       '🔐',
	};
	const ROLE_COLORS: Record<string, string> = {
		ogrenci:     'from-sky-500 to-sky-600',
		Akademisyen: 'from-violet-500 to-violet-600',
		Admin:       'from-rose-500 to-rose-600',
	};
	const ROLE_LABELS: Record<string, string> = {
		ogrenci:     'Öğrenci Paneli',
		Akademisyen: 'Akademisyen Paneli',
		Admin:       'Admin Paneli',
	};

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		try {
			const [roleRes, seedRes] = await Promise.allSettled([
				devGetObsRole(token),
				devSeedUsers(token),
			]);
			if (roleRes.status === 'fulfilled') {
				currentRole  = roleRes.value.obs_role;
				currentEmail = roleRes.value.email;
			}
			if (seedRes.status === 'fulfilled') {
				accounts = seedRes.value.accounts;
			}
		} catch (e: unknown) {
			err = e instanceof Error ? e.message : 'Hata oluştu.';
		} finally { loading = false; }
	});

	function switchRole(obsRole: string) {
		if (!browser) return;
		localStorage.setItem('obsRoleOverride', obsRole);
		const path = obsRole === 'Admin' ? '/obs/admin' : obsRole === 'Akademisyen' ? '/obs/akademisyen' : '/obs/ogrenci';
		goto(path);
	}

	async function reseed() {
		seeding = true; err = null;
		const token = localStorage.token ?? null;
		try {
			const r = await devSeedUsers(token);
			accounts = r.accounts;
		} catch (e: unknown) {
			err = e instanceof Error ? e.message : 'Seed hatası.';
		} finally { seeding = false; }
	}
</script>

<svelte:head><title>OBS — Dev Giriş Paneli</title></svelte:head>

<div class="flex min-h-screen flex-col items-center justify-center gap-6 bg-gradient-to-br from-slate-100 to-slate-200 p-6 dark:from-slate-950 dark:to-slate-900">

	<!-- Başlık -->
	<div class="text-center">
		<div class="text-2xl font-black tracking-tight text-slate-800 dark:text-slate-100">
			OBS — Geliştirici Paneli
		</div>
		<div class="mt-1 text-sm text-slate-500 dark:text-slate-400">
			Rol değiştirme ve test hesapları
		</div>
		{#if currentEmail}
			<div class="mt-2 inline-block rounded-full bg-slate-200 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
				Oturum: <strong>{currentEmail}</strong>
			</div>
		{/if}
	</div>

	<!-- Hata -->
	{#if err}
		<div class="w-full max-w-md rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
			{err}
		</div>
	{/if}

	<!-- Rol geçiş kartları -->
	<div class="grid w-full max-w-md grid-cols-1 gap-3 sm:grid-cols-3">
		{#each ['ogrenci','Akademisyen','Admin'] as role}
			<button
				on:click={() => switchRole(role)}
				type="button"
				class="group flex flex-col items-center gap-2 rounded-2xl bg-gradient-to-b {ROLE_COLORS[role]} p-5 text-white shadow-lg transition hover:scale-105 hover:shadow-xl active:scale-95
					{currentRole === role ? 'ring-4 ring-white/50' : ''}">
				<span class="text-3xl">{ROLE_ICONS[role]}</span>
				<span class="text-sm font-bold">{ROLE_LABELS[role]}</span>
				{#if currentRole === role}
					<span class="rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-semibold">Aktif</span>
				{/if}
			</button>
		{/each}
	</div>

	<!-- Test hesapları -->
	<div class="w-full max-w-md rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="flex items-center justify-between border-b border-black/5 px-5 py-3 dark:border-white/10">
			<span class="text-sm font-bold text-slate-700 dark:text-slate-200">Test Hesapları</span>
			<button on:click={reseed} disabled={seeding} type="button"
				class="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 disabled:opacity-50 dark:bg-white/10 dark:text-slate-300 dark:hover:bg-white/20 transition">
				{seeding ? 'Oluşturuluyor…' : '↺ Yeniden Oluştur'}
			</button>
		</div>

		{#if loading}
			<div class="px-5 py-8 text-center text-sm text-slate-400">Yükleniyor…</div>
		{:else if accounts.length === 0}
			<div class="px-5 py-8 text-center text-sm text-slate-400">
				Hesap oluşturulamadı. Backend başlatılmış mı?
			</div>
		{:else}
			<div class="divide-y divide-black/5 dark:divide-white/10">
				{#each accounts as acc}
					<div class="flex items-center justify-between px-5 py-3">
						<div>
							<div class="flex items-center gap-2">
								<span class="text-base">{ROLE_ICONS[acc.obs_role] ?? '👤'}</span>
								<span class="text-sm font-semibold text-slate-800 dark:text-slate-100">{acc.name}</span>
								{#if acc.existed}
									<span class="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-500 dark:bg-white/10 dark:text-slate-400">Mevcut</span>
								{:else}
									<span class="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400">Yeni</span>
								{/if}
							</div>
							<div class="mt-0.5 font-mono text-xs text-slate-500">{acc.email}</div>
						</div>
						<div class="text-right">
							<div class="font-mono text-xs font-bold text-sky-600 dark:text-sky-400">{acc.password}</div>
							<button on:click={() => switchRole(acc.obs_role)} type="button"
								class="mt-1 rounded-lg bg-gradient-to-r {ROLE_COLORS[acc.obs_role] ?? 'from-slate-500 to-slate-600'} px-2.5 py-1 text-[10px] font-bold text-white transition hover:opacity-90">
								Geç →
							</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}

		<div class="border-t border-black/5 px-5 py-3 dark:border-white/10">
			<p class="text-xs text-slate-400 dark:text-slate-500">
				⚠️ Bu sayfa sadece geliştirme ortamında görünür. Canlıya çıkmadan önce kaldırılacak.
			</p>
		</div>
	</div>

	<!-- Geri dön -->
	<a href="/obs" class="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition">
		← OBS Ana Sayfası
	</a>
</div>
