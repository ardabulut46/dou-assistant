<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { onDestroy, onMount } from 'svelte';
	import { user } from '$lib/stores';
	import { userSignOut } from '$lib/apis/auths';
	import { getDouInbox, getDouAcademicApprovalRequests } from '$lib/apis/douAcademic';

	export let title = 'Öğrenci Bilgi Sistemi';
	export let subtitle = 'Doğuş Üniversitesi';
	export let termLabel = '2025-2026 Bahar';
	export let activePath: string = '/obs';
	export let role: 'ogrenci' | 'akademisyen' | 'admin' = 'ogrenci';

	type NavItem = { label: string; href: string; badge?: number };
	type NavGroup = { section: string; items: NavItem[] };

	// ---------------------------------------------------------------------------
	// Öğrenci nav
	// ---------------------------------------------------------------------------
	const ogrenciGroups: NavGroup[] = [
		{
			section: 'GENEL',
			items: [
				{ label: 'Özlük Bilgileri', href: '/obs/ogrenci/ozluk-bilgileri' },
				{ label: 'Akademik Takvim', href: '/obs/ogrenci/akademik-takvim' },
				{ label: 'Danışman Bilgileri', href: '/obs/ogrenci/danisman-bilgileri' },
				{ label: 'Müfredat Durumu', href: '/obs/ogrenci/mufredat' },
				{ label: 'Alınan Dersler', href: '/obs/ogrenci/alinan-dersler' },
				{ label: 'Ders Programı', href: '/obs/ogrenci/ders-programi' },
				{ label: 'Sınav Takvimi', href: '/obs/ogrenci/sinav-takvimi' }
			]
		},
		{
			section: 'DERS İŞLEMLERİ',
			items: [
				{ label: 'Ders Kayıt', href: '/obs/ogrenci/ders-kayit' },
				{ label: 'Ders Ekle / Bırak', href: '/obs/ogrenci/ders-ekle-birak' },
				{ label: 'Not Listesi', href: '/obs/ogrenci/not-listesi' },
				{ label: 'Dönem Ortalamaları', href: '/obs/ogrenci/donem-ortalamalari' },
				{ label: 'Transkript', href: '/obs/ogrenci/transkript' },
				{ label: 'Devamsızlık Durumu', href: '/obs/ogrenci/devamsizlik-durumu' }
			]
		},
		{
			section: 'İLETİŞİM',
			items: [
				{ label: 'Gelen Mesajlar', href: '/obs/ogrenci/mesajlar-gelen' },
				{ label: 'Gönderilen Mesajlar', href: '/obs/ogrenci/mesajlar-gonderilen' },
				{ label: 'Belge Talebi', href: '/obs/ogrenci/belge-talebi' },
				{ label: 'Duyurular', href: '/obs/ogrenci/duyurular' },
				{ label: 'Şifre Değiştir', href: '/obs/ogrenci/sifre-degistir' }
			]
		}
	];

	// ---------------------------------------------------------------------------
	// Akademisyen nav
	// ---------------------------------------------------------------------------
	const akademisyenGroups: NavGroup[] = [
		{
			section: 'ŞUBELERİM',
			items: [
				{ label: 'Şubelerim', href: '/obs/akademisyen/subelerim' },
				{ label: 'Not Girişi', href: '/obs/akademisyen/not-girisi' },
				{ label: 'Yoklama Girişi', href: '/obs/akademisyen/yoklama-girisi' },
				{ label: 'Sınav Tanımlama', href: '/obs/akademisyen/sinav-tanimlama' }
			]
		},
		{
			section: 'DANIŞMANLIK',
			items: [
				{ label: 'Öğrencilerim', href: '/obs/akademisyen/danismanlik-ogrencilerim' },
				{ label: 'Onay Talepleri', href: '/obs/akademisyen/onay-talepleri' }
			]
		},
		{
			section: 'İLETİŞİM',
			items: [
				{ label: 'Duyuru Oluştur', href: '/obs/akademisyen/duyuru-olustur' },
				{ label: 'Gelen Mesajlar', href: '/obs/akademisyen/mesajlar-gelen' },
				{ label: 'Gönderilen Mesajlar', href: '/obs/akademisyen/mesajlar-gonderilen' }
			]
		},
		{
			section: 'HESAP',
			items: [{ label: 'Şifre Değiştir', href: '/obs/akademisyen/sifre-degistir' }]
		}
	];

	// ---------------------------------------------------------------------------
	// Admin nav
	// ---------------------------------------------------------------------------
	const adminGroups: NavGroup[] = [
		{
			section: 'KULLANICI',
			items: [
				{ label: 'Kullanıcı Yönetimi', href: '/obs/admin/kullanici-yonetimi' },
				{ label: 'Danışman Atama', href: '/obs/admin/danisman-atama' },
				{ label: 'Şube — Öğretim Üyesi Atama', href: '/obs/admin/danisman-ve-ders-atama' },
				{ label: 'Rol Yönetimi', href: '/obs/admin/rol-yonetimi' }
			]
		},
		{
			section: 'AKADEMİK KATALOG',
			items: [
				{ label: 'Bölüm Yönetimi', href: '/obs/admin/bolum-yonetimi' },
				{ label: 'Dönem Yönetimi', href: '/obs/admin/donem-yonetimi' },
				{ label: 'Ders Kataloğu', href: '/obs/admin/ders-katalogu' },
				{ label: 'Şube Açma', href: '/obs/admin/sube-acma' },
				{ label: 'Derslik Yönetimi', href: '/obs/admin/derslik-yonetimi' }
			]
		},
		{
			section: 'SİSTEM',
			items: [
				{ label: 'Akademik Takvim', href: '/obs/admin/akademik-takvim' },
				{ label: 'Kayıt Kuralları', href: '/obs/admin/kayit-kurallari' },
				{ label: 'Duyuru (Global)', href: '/obs/admin/duyuru-global' },
				{ label: 'Audit Kayıtları', href: '/obs/admin/audit-kayitlari' }
			]
		}
	];

	const roleGroups: Record<string, NavGroup[]> = {
		ogrenci: ogrenciGroups,
		akademisyen: akademisyenGroups,
		admin: adminGroups
	};

	const roleDashboard: Record<string, string> = {
		ogrenci: '/obs/ogrenci',
		akademisyen: '/obs/akademisyen',
		admin: '/obs/admin'
	};

	const roleLabel: Record<string, string> = {
		ogrenci: 'Öğrenci Paneli',
		akademisyen: 'Akademisyen Paneli',
		admin: 'Admin Paneli'
	};

	$: navGroups = roleGroups[role] ?? ogrenciGroups;
	$: dashHref = roleDashboard[role] ?? '/obs/ogrenci';
	$: panelLabel = roleLabel[role] ?? 'OBS';

	/** Sondaki / tutarsızlığını kaldır; menüde yalnızca en spesifik (en uzun) eşleşen öğe aktif olsun */
	$: normalizedActive = (activePath ?? '').replace(/\/+$/, '') || dashHref;
	$: navFlat = navGroups.flatMap((g) => g.items);
	$: activeNavHref = (() => {
		const p = normalizedActive;
		let best = '';
		for (const it of navFlat) {
			const h = it.href;
			if (p === h || p.startsWith(h + '/')) {
				if (h.length > best.length) best = h;
			}
		}
		return best;
	})();
	const isActive = (href: string) => href === activeNavHref;

	$: aiAskHref = `/?back=${encodeURIComponent(normalizedActive)}`;

	// ---------------------------------------------------------------------------
	// Bildirimler — inbox + approval'dan dinamik
	// ---------------------------------------------------------------------------
	type Notif = {
		id: string;
		type: 'grade' | 'message' | 'attendance' | 'info' | 'approval';
		text: string;
		time: string;
		read: boolean;
	};

	let notifOpen = false;
	let notifications: Notif[] = [];

	async function loadNotifications() {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;

		const fresh: Notif[] = [];

		// Gelen kutusu → okunmamış mesajlar bildirim olarak
		const inboxRes = await getDouInbox(token).catch(() => null);
		if (inboxRes?.messages) {
			for (const m of inboxRes.messages) {
				if (!m.is_read) {
					fresh.unshift({
						id: `notif-msg-${m.id}`,
						type: 'message',
						text: `${m.sender_name ?? 'Biri'}: ${m.subject}`,
						time: m.sent_at
							? new Date(m.sent_at).toLocaleTimeString('tr-TR', {
									hour: '2-digit',
									minute: '2-digit'
								})
							: '',
						read: false
					});
				}
			}
		}

		// Akademisyen ise → bekleyen onay talepleri bildirim olarak
		if (role === 'akademisyen') {
			const aprRes = await getDouAcademicApprovalRequests(token).catch(() => null);
			if (aprRes?.requests) {
				const pending = aprRes.requests.filter((r: { status: string }) => r.status === 'pending');
				if (pending.length) {
					fresh.unshift({
						id: 'notif-approvals',
						type: 'approval',
						text: `${pending.length} bekleyen ders onay talebi var`,
						time: 'şimdi',
						read: false
					});
				}
			}
		}

		notifications = fresh;
	}

	$: unreadCount = notifications.filter((n) => !n.read).length;

	function markAllRead() {
		notifications = notifications.map((n) => ({ ...n, read: true }));
	}

	const notifIcon: Record<string, string> = {
		grade: '📊',
		message: '✉️',
		attendance: '⚠️',
		info: 'ℹ️',
		approval: '✅'
	};

	// ---------------------------------------------------------------------------
	// Idle timeout (20 dakika)
	// ---------------------------------------------------------------------------
	const IDLE_MS = 20 * 60 * 1000;
	let idleTimer: ReturnType<typeof setTimeout> | null = null;
	let idleWarning = false;
	let warnTimer: ReturnType<typeof setTimeout> | null = null;

	function resetIdle() {
		idleWarning = false;
		if (idleTimer) clearTimeout(idleTimer);
		if (warnTimer) clearTimeout(warnTimer);
		// 18 dk sonra uyarı
		warnTimer = setTimeout(
			() => {
				idleWarning = true;
			},
			IDLE_MS - 2 * 60 * 1000
		);
		// 20 dk sonra çıkış
		idleTimer = setTimeout(doLogout, IDLE_MS);
	}

	// ---------------------------------------------------------------------------
	// Logout
	// ---------------------------------------------------------------------------
	let loggingOut = false;

	async function doLogout() {
		if (!browser || loggingOut) return;
		loggingOut = true;
		localStorage.removeItem('obsRoleOverride');
		try {
			const res = await userSignOut();
			// @ts-expect-error Dinamik import ile store sıfırlama (tip paketi dışı)
			import('$lib/stores').then(({ user: u }) => u.set(null));
			localStorage.removeItem('token');
			location.href = res?.redirect_url ?? '/auth';
		} catch {
			location.href = '/auth';
		}
	}

	// ---------------------------------------------------------------------------
	// Lifecycle
	// ---------------------------------------------------------------------------
	onMount(() => {
		if (!browser) return;
		const events = ['mousemove', 'keydown', 'mousedown', 'touchstart', 'scroll'];
		events.forEach((e) => window.addEventListener(e, resetIdle, { passive: true }));
		resetIdle();
		loadNotifications();
	});

	onDestroy(() => {
		if (idleTimer) clearTimeout(idleTimer);
		if (warnTimer) clearTimeout(warnTimer);
	});
</script>

<!-- Idle uyarı banner -->
{#if idleWarning}
	<div
		class="fixed top-0 left-0 right-0 z-[100] flex items-center justify-between bg-amber-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg"
	>
		<span>⏰ 2 dakika hareketsizlik algılandı — oturum kapanmak üzere.</span>
		<button
			on:click={resetIdle}
			type="button"
			class="rounded-lg bg-white/20 px-3 py-1 text-xs hover:bg-white/30"
		>
			Devam Et
		</button>
	</div>
{/if}

<svelte:head>
	<title>{title}</title>
</svelte:head>

<div
	class="min-h-[100dvh] bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
	class:pt-10={idleWarning}
	aria-label={title}
>
	<div class="flex h-[100dvh] min-h-0">
		<!-- Sidebar -->
		<aside class="flex w-[260px] shrink-0 flex-col overflow-y-auto bg-slate-950 text-slate-100">
			<!-- Header -->
			<div class="px-5 py-4 shadow-[0_1px_0_rgba(255,255,255,0.06)]">
				<a href={dashHref} class="flex items-center gap-3 transition-opacity hover:opacity-80">
					<div
						class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-sky-500/20 ring-1 ring-sky-400/30 text-sm font-bold text-sky-400"
					>
						{($user?.name ?? 'U').charAt(0).toUpperCase()}
					</div>
					<div class="min-w-0">
						<div class="truncate text-sm font-semibold leading-tight">
							{$user?.name ?? subtitle}
						</div>
						<div class="mt-0.5 truncate text-[11px] font-medium text-sky-400/80">{panelLabel}</div>
					</div>
				</a>
			</div>

			<!-- Nav -->
			<nav class="flex-1 overflow-y-auto overflow-x-hidden px-3 pb-4 pt-2">
				<div class="mb-3 px-3">
					<div class="mb-1 text-[10px] font-bold tracking-widest text-slate-500">ASİSTAN</div>
					<a
						href={aiAskHref}
						class="flex w-full items-center gap-2 rounded-lg bg-sky-500/15 px-3 py-2 text-[13px] font-semibold text-sky-300 ring-1 ring-sky-500/25 transition-colors hover:bg-sky-500/25"
					>
						<span aria-hidden="true">✨</span>
						<span>AI Asistan</span>
					</a>
				</div>
				{#each navGroups as group}
					<div class="mb-1 mt-4 px-3 text-[10px] font-bold tracking-widest text-slate-500">
						{group.section}
					</div>
					{#each group.items as item}
						<a
							href={item.href}
							aria-current={isActive(item.href) ? 'page' : undefined}
							class="flex w-full items-center justify-between rounded-lg px-3 py-2 text-[13px] leading-5 transition-all
								{isActive(item.href)
								? 'bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/20'
								: 'text-slate-300 hover:bg-white/[0.08] hover:text-white'}"
						>
							<span class="min-w-0 truncate">{item.label}</span>
							{#if item.badge && item.badge > 0}
								<span
									class="ml-2 shrink-0 rounded-full bg-red-500 px-1.5 py-0.5 text-[9px] font-bold text-white leading-none"
									>{item.badge}</span
								>
							{:else if isActive(item.href)}
								<span class="ml-2 shrink-0 text-[10px] text-sky-400">●</span>
							{/if}
						</a>
					{/each}
				{/each}
			</nav>

			<!-- Çıkış -->
			<div class="border-t border-white/10 px-4 py-3">
				<button
					on:click={doLogout}
					disabled={loggingOut}
					type="button"
					class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-medium text-red-400 transition-colors hover:bg-red-500/15 hover:text-red-300 disabled:opacity-50"
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
					>
						<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
						<polyline points="16 17 21 12 16 7" />
						<line x1="21" y1="12" x2="9" y2="12" />
					</svg>
					{loggingOut ? 'Çıkılıyor…' : 'Oturumu Kapat'}
				</button>
			</div>
		</aside>

		<!-- Main: flex içinde kaydırma için min-h-0 + overflow -->
		<div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
			<!-- Topbar -->
			<header
				class="sticky top-0 z-10 border-b border-black/10 bg-white/95 px-6 py-3 backdrop-blur dark:border-white/10 dark:bg-slate-950/90"
			>
				<div class="flex items-center justify-between gap-4">
					<div class="min-w-0">
						<div class="truncate text-sm font-semibold">{termLabel}</div>
						<div class="truncate text-xs text-slate-500 dark:text-slate-400">
							<slot name="userline" />
						</div>
					</div>

					<div class="flex shrink-0 items-center gap-2">
						<!-- Bildirim çanı -->
						<div class="relative">
							<button
								on:click={() => {
									notifOpen = !notifOpen;
									if (notifOpen) markAllRead();
								}}
								type="button"
								class="relative flex size-9 items-center justify-center rounded-lg border border-black/10 bg-white text-slate-600 transition-colors hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
								title="Bildirimler"
							>
								<svg
									class="size-4"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
								>
									<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
									<path d="M13.73 21a2 2 0 0 1-3.46 0" />
								</svg>
								{#if unreadCount > 0}
									<span
										class="absolute -right-1 -top-1 flex size-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white"
										>{unreadCount}</span
									>
								{/if}
							</button>

							{#if notifOpen}
								<!-- Backdrop -->
								<button
									class="fixed inset-0 z-40"
									on:click={() => (notifOpen = false)}
									type="button"
									aria-label="Kapat"
								></button>
								<!-- Dropdown -->
								<div
									class="absolute right-0 top-11 z-50 w-80 overflow-hidden rounded-xl border border-black/10 bg-white shadow-2xl dark:border-white/10 dark:bg-slate-900"
								>
									<div
										class="flex items-center justify-between border-b border-black/5 px-4 py-3 dark:border-white/10"
									>
										<span class="text-sm font-bold">Bildirimler</span>
										<button
											on:click={markAllRead}
											type="button"
											class="text-xs text-sky-500 hover:text-sky-400">Tümünü okundu işaretle</button
										>
									</div>
									{#each notifications as n}
										{@const notifHref =
											n.type === 'message'
												? role === 'akademisyen'
													? '/obs/akademisyen/mesajlar-gelen'
													: '/obs/ogrenci/mesajlar-gelen'
												: n.type === 'approval'
													? '/obs/akademisyen/onay-talepleri'
													: n.type === 'grade'
														? '/obs/ogrenci/not-listesi'
														: null}
										<button
											on:click={() => {
												notifOpen = false;
												if (notifHref) goto(notifHref);
											}}
											type="button"
											class="flex w-full items-start gap-3 border-b border-black/5 px-4 py-3 text-left transition-colors last:border-0 dark:border-white/5
												{n.read ? 'opacity-60' : 'bg-sky-50/50 dark:bg-sky-950/20'}
												{notifHref ? 'cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5' : 'cursor-default'}"
										>
											<span class="mt-0.5 text-base">{notifIcon[n.type] ?? 'ℹ️'}</span>
											<div class="min-w-0 flex-1">
												<div class="text-xs font-medium leading-snug">{n.text}</div>
												<div class="mt-0.5 text-[10px] text-slate-400">{n.time}</div>
											</div>
											{#if !n.read}<span class="mt-1 size-2 shrink-0 rounded-full bg-sky-500"
												></span>{/if}
										</button>
									{:else}
										<div class="px-4 py-6 text-center text-sm text-slate-400">Bildirim yok.</div>
									{/each}
									<!-- Tüm bildirimleri yenile -->
									<button
										on:click={() => {
											loadNotifications();
											notifOpen = false;
										}}
										type="button"
										class="w-full border-t border-black/5 px-4 py-2.5 text-center text-xs text-slate-400 hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5 transition-colors"
									>
										↺ Bildirimleri Yenile
									</button>
								</div>
							{/if}
						</div>

						<a
							href={aiAskHref}
							class="rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-sky-400"
						>
							AI'a Sor
						</a>
						<a
							href="/"
							class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm transition-colors hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
						>
							← Asistan
						</a>
						<slot name="actions" />
					</div>
				</div>
			</header>

			<!-- Content -->
			<main class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
				<slot />
			</main>
		</div>
	</div>
</div>
