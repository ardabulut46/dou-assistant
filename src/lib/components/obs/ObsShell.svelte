<script lang="ts">
	import { browser } from '$app/environment';
	import { goto, afterNavigate } from '$app/navigation';
	import { onDestroy, onMount } from 'svelte';
	import { user } from '$lib/stores';
	import { userSignOut } from '$lib/apis/auths';
	import { OBS_PORTAL_ROLE_PICK_KEY } from '$lib/obs/obsAccess';
	import {
		getDouInbox,
		getDouAcademicApprovalRequests,
		markDouMessageRead,
		getDouStudentAnnouncements,
		getDouAcademicAnnouncements,
		getDouAdminAnnouncements,
		getDouStudentAttendance,
		postDouClientAuditEvent,
		type DouAnnouncement
	} from '$lib/apis/douAcademic';

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
				{ label: 'Not Hesaplama', href: '/obs/ogrenci/not-hesaplama' },
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

	const OBS_ANN_SEEN_LS_KEY = 'dou_obs_ann_seen_ids';
	const OBS_ATT_WARN_FP_LS_KEY = 'dou_obs_attendance_low_fp';

	/** Küçük ekran: yan menü çekmece; md+ masaüstü görünüm değişmez. */
	let mobileNavOpen = false;

	/** OBS içinde sayfa görüntüleme audit (aynı pathname tekrarını tek kayıtta tutar). */
	let lastLoggedObsPath = '';

	afterNavigate(({ to }) => {
		mobileNavOpen = false;
		if (!browser) return;
		const pathname = (to?.url?.pathname ?? '').replace(/\/+$/, '') || '/';
		if (!pathname.startsWith('/obs')) {
			lastLoggedObsPath = '';
			return;
		}
		const token = typeof localStorage !== 'undefined' ? localStorage.token : '';
		if (!token) return;
		if (pathname === lastLoggedObsPath) return;
		lastLoggedObsPath = pathname;
		void postDouClientAuditEvent(token, {
			action: 'ui.page_view',
			entity_type: 'obs_route',
			path: pathname,
			label: `OBS: ${pathname}`,
			details: { route: pathname, role }
		}).catch(() => {});
	});

	/** Çan rozeti için markAllRead’de yazılacak son fingerprint (bir yüklemede hesaplanır). */
	let lastAttendanceLowFingerprint = '';

	function loadAnnSeenSet(): Set<string> {
		if (!browser) return new Set();
		try {
			const raw = localStorage.getItem(OBS_ANN_SEEN_LS_KEY);
			const arr = raw ? (JSON.parse(raw) as unknown) : [];
			return new Set(Array.isArray(arr) ? arr.map(String) : []);
		} catch {
			return new Set();
		}
	}

	function persistAnnSeenSet(seen: Set<string>) {
		if (!browser) return;
		try {
			localStorage.setItem(OBS_ANN_SEEN_LS_KEY, JSON.stringify([...seen]));
		} catch {
			/* yok */
		}
	}

	function markAnnouncementIdsSeen(ids: string[]) {
		if (!ids.length) return;
		const s = loadAnnSeenSet();
		for (const id of ids) s.add(id);
		persistAnnSeenSet(s);
	}

	function loadAttendanceWarnSeenFingerprint(): string {
		if (!browser) return '';
		try {
			return (localStorage.getItem(OBS_ATT_WARN_FP_LS_KEY) ?? '').trim();
		} catch {
			return '';
		}
	}

	function persistAttendanceWarnFingerprint(fp: string) {
		if (!browser || !fp) return;
		try {
			localStorage.setItem(OBS_ATT_WARN_FP_LS_KEY, fp);
		} catch {
			/* yok */
		}
	}

	function attendanceLowCoursesFingerprint(rows: { course_code: string; attendance_pct: number }[]) {
		return rows
			.map((r) => `${String(r.course_code ?? '').trim()}:${Math.round(Number(r.attendance_pct) * 10) / 10}`)
			.sort()
			.join('|');
	}

	async function fetchActiveAnnouncementsForRole(token: string | null): Promise<DouAnnouncement[]> {
		if (!token) return [];
		if (role === 'ogrenci') {
			const r = await getDouStudentAnnouncements(token).catch(() => null);
			return (r?.announcements ?? []).filter((x) => x.is_active);
		}
		if (role === 'akademisyen') {
			const r = await getDouAcademicAnnouncements(token).catch(() => null);
			return (r?.announcements ?? []).filter((x) => x.is_active);
		}
		if (role === 'admin') {
			const r = await getDouAdminAnnouncements(token).catch(() => null);
			return (r?.announcements ?? []).filter((x) => x.is_active);
		}
		return [];
	}

	async function markAllActiveAnnouncementsSeen(token: string | null) {
		const list = await fetchActiveAnnouncementsForRole(token);
		markAnnouncementIdsSeen(list.map((a) => a.id));
	}

	function annAudienceLabel(at: string): string {
		const a = (at || '').toLowerCase();
		const map: Record<string, string> = {
			all: 'Genel',
			student: 'Kişisel',
			section: 'Şube',
			department: 'Bölüm',
			advisees: 'Danışmanlık öğrencileri'
		};
		return map[a] ?? a;
	}

	// ---------------------------------------------------------------------------
	// Bildirimler — inbox + approval'dan dinamik
	// ---------------------------------------------------------------------------
	type Notif = {
		id: string;
		type: 'grade' | 'message' | 'attendance' | 'info' | 'approval' | 'announcement';
		text: string;
		time: string;
		/** Sıralama: en yeni üstte */
		sortMs: number;
		read: boolean;
		/** Gelen kutusu kaydı — sunucuya PATCH /messages/:id/read */
		messageId?: string;
		/** Duyuru satırı — okundu yerel (localStorage) */
		announcementId?: string;
	};

	let notifOpen = false;
	let notifications: Notif[] = [];
	/** Tüm gelen kutusundaki okunmamış mesaj sayısı (çan rakamı için). */
	let unreadInboxTotal = 0;
	/** Aktif duyurulardan henüz “görüldü” işaretlenmemiş olanlar (localStorage'a göre, çan rakamı). */
	let unreadAnnouncementsTotal = 0;
	/** Devamsızlık %70 altı uyarısı — fingerprint ile; çan rakamına +1 olabilir. */
	let unreadAttendanceWarnTotal = 0;
	/** "Tümünü okundu" sonrası panelde okumuş iletileri gösterme; çanı yeniden açınca sıfır. */
	let bellHideReadMsgsUntilReopen = false;

	const MAX_BELL_MESSAGES = 50;
	const BELL_POLL_MS = 55_000;

	let bellPollInterval: ReturnType<typeof setInterval> | null = null;
	/** İlk bildirim yüklemesinde (aynı OBS oturumu) bir kez ıslık çalınıp çalınmayacağı bayrağı */
	let bellIntroWhistlePlayed = false;

	/** Rozet sayısı > 0 iken OBS’ye ilk girişte tek seferlik ıslık (polling’de tekrarlanmaz). */
	function playBellIntroWhistle() {
		if (!browser) return;
		const AC =
			typeof AudioContext !== 'undefined'
				? AudioContext
				: (typeof (
						globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }
				  ).webkitAudioContext !== 'undefined'
					? (globalThis as typeof globalThis & { webkitAudioContext: typeof AudioContext })
							.webkitAudioContext
					: null);
		if (!AC) return;
		try {
			const ctx = new AC();
			const master = ctx.createGain();
			master.gain.value = 0.6;
			master.connect(ctx.destination);

			const runChirp = (t0: number, f0: number, f1: number) => {
				const osc = ctx.createOscillator();
				const g = ctx.createGain();
				osc.connect(g);
				g.connect(master);
				osc.type = 'triangle';
				osc.frequency.setValueAtTime(f0, t0);
				osc.frequency.exponentialRampToValueAtTime(f1, t0 + 0.07);
				const eps = 0.0008;
				g.gain.setValueAtTime(eps, t0);
				g.gain.linearRampToValueAtTime(0.88, t0 + 0.018);
				g.gain.exponentialRampToValueAtTime(eps, t0 + 0.085);
				osc.start(t0);
				osc.stop(t0 + 0.09);
			};

			void ctx.resume().then(() => {
				const t = ctx.currentTime + 0.02;
				runChirp(t, 2150, 3100);
				runChirp(t + 0.1, 2550, 3600);
			});

			window.setTimeout(() => {
				try {
					ctx.close();
				} catch {
					/* yok */
				}
			}, 400);
		} catch {
			/* oturum sessiz başarısız / autoplay kısıtı */
		}
	}

	async function loadNotifications(opts?: { dingOnUnread?: boolean }) {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;

		lastAttendanceLowFingerprint = '';
		unreadAttendanceWarnTotal = 0;

		const fresh: Notif[] = [];
		const seenAnn = loadAnnSeenSet();

		const inboxRes = await getDouInbox(token).catch(() => null);
		const msgsRaw = inboxRes?.messages ?? [];
		unreadInboxTotal = msgsRaw.filter((m) => !m.is_read).length;

		let ordered = [...msgsRaw].sort((a, b) => {
			const ta = a.sent_at ? new Date(a.sent_at).getTime() : 0;
			const tb = b.sent_at ? new Date(b.sent_at).getTime() : 0;
			return tb - ta;
		});
		if (bellHideReadMsgsUntilReopen) {
			ordered = ordered.filter((m) => !m.is_read);
		}

		for (const m of ordered.slice(0, MAX_BELL_MESSAGES)) {
			const sortMs = m.sent_at ? new Date(m.sent_at).getTime() : 0;
			fresh.push({
				id: `notif-msg-${m.id}`,
				type: 'message',
				messageId: m.id,
				text: `${m.sender_name ?? 'Biri'}: ${m.subject}`,
				time: m.sent_at
					? new Date(m.sent_at).toLocaleTimeString('tr-TR', {
							hour: '2-digit',
							minute: '2-digit'
						})
					: '',
				sortMs,
				read: !!m.is_read
			});
		}

		const annList = await fetchActiveAnnouncementsForRole(token);

		let unseenAnnCount = 0;
		for (const a of annList) {
			const seenRow = seenAnn.has(a.id);
			if (!seenRow) unseenAnnCount += 1;
			const ts = a.published_at || a.created_at;
			const sortMs = ts ? new Date(ts).getTime() : 0;
			const timeStr = ts
				? new Date(ts).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })
				: '';
			const scope = annAudienceLabel(a.audience_type);
			fresh.push({
				id: `notif-ann-${a.id}`,
				type: 'announcement',
				announcementId: a.id,
				text: `[${scope}] ${a.title}`,
				time: timeStr,
				sortMs,
				read: seenRow
			});
		}
		unreadAnnouncementsTotal = unseenAnnCount;

		/** Öğrenci: en az bir derste katılım %70 altıysa bildirim (aynı parmak izi görüldü sayılmışsa rozette sayılmaz). */
		if (role === 'ogrenci') {
			const attRes = await getDouStudentAttendance(token).catch(() => null);
			const lowCourses = (attRes?.attendance ?? []).filter((r) => r.attendance_pct < 70);
			if (lowCourses.length) {
				lastAttendanceLowFingerprint = attendanceLowCoursesFingerprint(lowCourses);
				const seenFp = loadAttendanceWarnSeenFingerprint();
				const attRead = seenFp === lastAttendanceLowFingerprint;
				unreadAttendanceWarnTotal = attRead ? 0 : 1;
				const preview = lowCourses
					.slice(0, 3)
					.map((r) => `${String(r.course_code || '').trim()} %${r.attendance_pct}`)
					.join(', ');
				const more =
					lowCourses.length > 3 ? ` ve ${lowCourses.length - 3} ders daha` : '';
				fresh.push({
					id: 'notif-attendance-low',
					type: 'attendance',
					text: `${lowCourses.length} derste katılım oranı %70'in altında (${preview}${more}). Devamsızlık Durumu ekranından kontrol edin.`,
					time: 'Kritik',
					sortMs: Date.now() + 86_200_000,
					read: attRead
				});
			} else if (browser) {
				try {
					localStorage.removeItem(OBS_ATT_WARN_FP_LS_KEY);
				} catch {
					/* yok */
				}
			}
		}

		fresh.sort((x, y) => y.sortMs - x.sortMs);
		let merged = fresh.slice(0, MAX_BELL_MESSAGES);

		// Akademisyen ise → bekleyen onay talepleri bildirim olarak (her zaman üstte)
		if (role === 'akademisyen') {
			const aprRes = await getDouAcademicApprovalRequests(token).catch(() => null);
			if (aprRes?.requests) {
				const pending = aprRes.requests.filter((r: { status: string }) => r.status === 'pending');
				if (pending.length) {
					const nowMs = Date.now();
					merged.unshift({
						id: 'notif-approvals',
						type: 'approval',
						text: `${pending.length} bekleyen ders onay talebi var`,
						time: 'şimdi',
						sortMs: nowMs + 86400000,
						read: false
					});
					if (merged.length > MAX_BELL_MESSAGES) merged = merged.slice(0, MAX_BELL_MESSAGES);
				}
			}
		}

		notifications = merged;

		if (opts?.dingOnUnread && !bellIntroWhistlePlayed) {
			const hasApprovalRow = merged.some((n) => n.type === 'approval');
			const totalUnread =
				unreadInboxTotal + (hasApprovalRow ? 1 : 0) + unseenAnnCount + unreadAttendanceWarnTotal;
			if (totalUnread > 0) {
				bellIntroWhistlePlayed = true;
				queueMicrotask(() => playBellIntroWhistle());
			}
		}
	}
	$: unreadBellApproval = notifications.some((n) => n.type === 'approval');
	$: unreadCount =
		unreadInboxTotal +
		(unreadBellApproval ? 1 : 0) +
		unreadAnnouncementsTotal +
		unreadAttendanceWarnTotal;

	/** Gelen kutusu mesajlarını sunucuda okundu yapar; toplu sonrası panelden mesaj satırlarını düşürür (çanı tekrar açınca geçmiş gelir). */
	async function markAllRead() {
		if (!browser) return;
		const token = localStorage.token ?? null;
		/* Tüm aktif duyuruları görüldü say (panele sığmayanlar dahil) */
		await markAllActiveAnnouncementsSeen(token);
		persistAttendanceWarnFingerprint(lastAttendanceLowFingerprint);

		const inboxFresh = await getDouInbox(token).catch(() => null);
		const unreadIds =
			inboxFresh?.messages?.filter((m) => !m.is_read).map((m) => m.id) ?? [];

		if (token && unreadIds.length) {
			await Promise.allSettled(unreadIds.map((id) => markDouMessageRead(token, id)));
		}
		bellHideReadMsgsUntilReopen = true;
		await loadNotifications();
	}

	async function onNotifRowClick(n: Notif, notifHref: string | null) {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (n.type === 'announcement' && n.announcementId) {
			markAnnouncementIdsSeen([n.announcementId]);
		}
		if (n.type === 'attendance') {
			persistAttendanceWarnFingerprint(lastAttendanceLowFingerprint);
		}
		if (token && n.type === 'message' && n.messageId && !n.read) {
			try {
				await markDouMessageRead(token, n.messageId);
			} catch {
				/* yapılmış veya oturum */
			}
		}
		notifOpen = false;
		if (notifHref) await goto(notifHref);
		await loadNotifications();
	}

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
			sessionStorage.removeItem(OBS_PORTAL_ROLE_PICK_KEY);
			location.href = res?.redirect_url ?? '/auth';
		} catch {
			sessionStorage.removeItem(OBS_PORTAL_ROLE_PICK_KEY);
			location.href = '/auth';
		}
	}

	// ---------------------------------------------------------------------------
	// Lifecycle
	// ---------------------------------------------------------------------------
	function onEscapeCloseNav(e: KeyboardEvent) {
		if (e.key === 'Escape') mobileNavOpen = false;
	}

	onMount(() => {
		if (!browser) return;
		window.addEventListener('keydown', onEscapeCloseNav);
		const events = ['mousemove', 'keydown', 'mousedown', 'touchstart', 'scroll'];
		events.forEach((e) => window.addEventListener(e, resetIdle, { passive: true }));
		resetIdle();
		void loadNotifications({ dingOnUnread: true });
		bellPollInterval = setInterval(() => {
			void loadNotifications();
		}, BELL_POLL_MS);
	});

	onDestroy(() => {
		if (browser) window.removeEventListener('keydown', onEscapeCloseNav);
		if (idleTimer) clearTimeout(idleTimer);
		if (warnTimer) clearTimeout(warnTimer);
		if (bellPollInterval !== null) {
			clearInterval(bellPollInterval);
			bellPollInterval = null;
		}
	});
</script>

<!-- Idle uyarı banner -->
{#if idleWarning}
	<div
		class="fixed top-0 left-0 right-0 z-[100] flex items-center justify-between bg-amber-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg"
	>
		<span>2 dakika hareketsizlik algılandı — oturum kapanmak üzere.</span>
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
	class="flex h-[100dvh] max-h-[100dvh] min-h-0 flex-col overflow-hidden bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100 [touch-action:manipulation]"
	class:pt-10={idleWarning}
	aria-label={title}
>
	{#if mobileNavOpen}
		<button
			type="button"
			class="fixed inset-0 z-30 bg-black/50 backdrop-blur-[1px] md:hidden"
			aria-label="Menüyü kapat"
			on:click={() => (mobileNavOpen = false)}
		></button>
	{/if}
	<div class="flex min-h-0 flex-1">
		<!-- Sidebar: md+ sabit; küçük ekranda çekmece -->
		<aside
			id="obs-shell-drawer"
			class="fixed inset-y-0 left-0 z-40 flex min-h-0 w-[260px] max-w-[min(260px,88vw)] shrink-0 flex-col overflow-y-auto overflow-x-hidden overscroll-contain bg-slate-950 pl-[env(safe-area-inset-left,0)] text-slate-100 shadow-xl transition-transform duration-200 ease-out md:relative md:inset-auto md:z-0 md:flex md:max-w-none md:shadow-none {mobileNavOpen
				? 'translate-x-0'
				: '-translate-x-full md:translate-x-0'}"
		>
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
			<nav
				id="obs-shell-nav"
				class="flex-1 overflow-y-auto overflow-x-hidden px-3 pb-4 pt-2"
				aria-label="OBS ana menü"
			>
				<div class="mb-3 px-3">
					<a
						href={aiAskHref}
						class="flex w-full items-center gap-2 rounded-lg bg-sky-500/15 px-3 py-2 text-[13px] font-semibold text-sky-300 ring-1 ring-sky-500/25 transition-colors hover:bg-sky-500/25"
					>
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
				class="sticky top-0 z-10 shrink-0 border-b border-black/10 bg-white/95 px-4 py-3 pr-[calc(1rem+env(safe-area-inset-right,0px))] pl-[calc(1rem+env(safe-area-inset-left,0px))] backdrop-blur md:px-6 dark:border-white/10 dark:bg-slate-950/90"
			>
				<div class="flex items-center justify-between gap-3 md:gap-4">
					<div class="flex min-w-0 flex-1 items-start gap-2 md:block md:gap-0">
						<button
							type="button"
							class="mt-0.5 inline-flex size-10 shrink-0 items-center justify-center rounded-xl border border-black/10 bg-white text-slate-700 shadow-sm active:bg-slate-100 md:hidden dark:border-white/10 dark:bg-white/10 dark:text-slate-200 dark:active:bg-white/15"
							aria-label={mobileNavOpen ? 'Menüyü kapat' : 'Menüyü aç'}
							aria-expanded={mobileNavOpen}
							aria-controls="obs-shell-nav"
							on:click={() => (mobileNavOpen = !mobileNavOpen)}
						>
							{#if mobileNavOpen}
								<svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M18 6L6 18M6 6l12 12" />
								</svg>
							{:else}
								<svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<line x1="3" y1="6" x2="21" y2="6" />
									<line x1="3" y1="12" x2="21" y2="12" />
									<line x1="3" y1="18" x2="21" y2="18" />
								</svg>
							{/if}
						</button>
						<div class="min-w-0 pt-0.5 md:pt-0">
							<div class="truncate text-sm font-semibold">{termLabel}</div>
							<div class="truncate text-xs text-slate-500 dark:text-slate-400">
								<slot name="userline" />
							</div>
						</div>
					</div>

					<div class="flex shrink-0 items-center gap-2">
						<!-- Bildirim çanı -->
						<div class="relative">
							<button
								on:click={async () => {
									const opening = !notifOpen;
									notifOpen = opening;
									if (opening) {
										bellHideReadMsgsUntilReopen = false;
										await loadNotifications();
									}
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
									class="absolute right-0 top-11 z-50 max-w-[calc(100vw-1rem)] w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-black/10 bg-white shadow-2xl dark:border-white/10 dark:bg-slate-900"
								>
									<div
										class="flex items-center justify-between border-b border-black/5 px-4 py-3 dark:border-white/10"
									>
										<span class="text-sm font-bold">Bildirimler</span>
										<button
											on:click={() => void markAllRead()}
											type="button"
											class="text-xs text-sky-500 hover:text-sky-400">Tümünü okundu işaretle</button
										>
									</div>
									<div
										class="max-h-[min(22rem,calc(100dvh-10rem))] overflow-y-auto overflow-x-hidden overscroll-contain"
									>
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
															: n.type === 'attendance'
																? '/obs/ogrenci/devamsizlik-durumu'
																: n.type === 'announcement'
																	? role === 'ogrenci'
																		? '/obs/ogrenci/duyurular'
																		: role === 'akademisyen'
																			? '/obs/akademisyen/duyuru-olustur'
																			: role === 'admin'
																				? '/obs/admin/duyuru-global'
																				: null
																	: null}
											<button
												on:click={() => void onNotifRowClick(n, notifHref)}
												type="button"
												class="flex w-full items-start gap-3 border-b border-black/5 px-4 py-3 text-left transition-colors dark:border-white/5
													{n.read ? 'opacity-60' : 'bg-sky-50/50 dark:bg-sky-950/20'}
													{notifHref ? 'cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5' : 'cursor-default'}"
											>
												<div class="min-w-0 flex-1">
													<div class="text-xs font-medium leading-snug">{n.text}</div>
													<div class="mt-0.5 text-[10px] text-slate-400">{n.time}</div>
												</div>
												{#if !n.read}<span class="mt-1 size-2 shrink-0 rounded-full bg-sky-500"
													></span>{/if}
											</button>
										{:else}
											<div class="px-4 py-6 text-center text-sm text-slate-400">
												Bildirim yok.
											</div>
										{/each}
									</div>
									<!-- Tüm bildirimleri yenile -->
									<button
										on:click={() => {
											bellHideReadMsgsUntilReopen = false;
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
							class="hidden rounded-lg bg-sky-500 px-3 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-sky-400 sm:inline-flex sm:px-3 sm:text-sm"
						>
							AI Asistan
						</a>
						<slot name="actions" />
					</div>
				</div>
			</header>

			<!-- Content -->
			<main
				class="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain px-4 py-4 pb-[max(1.25rem,env(safe-area-inset-bottom,0px))] sm:px-6 sm:py-5 break-words"
			>
				<slot />
			</main>
		</div>
	</div>
</div>
