<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import { getDouAdminStats } from '$lib/apis/douAcademic';

	type Stats = {
		departments: number; terms: number; courses: number;
		classrooms: number; sections: number; announcements: number;
		users_total: number; users_active: number;
	};

	let stats: Stats | null = null;
	let loading = true;
	let statsErr: string | null = null;

	onMount(async () => {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) { loading = false; return; }
		try {
			stats = await getDouAdminStats(token) as unknown as Stats;
		} catch (e: unknown) {
			statsErr = e instanceof Error ? e.message : 'İstatistikler yüklenemedi.';
		} finally { loading = false; }
	});

	const modules = [
		{ href: '/obs/admin/kullanici-yonetimi', title: 'Kullanıcı Yönetimi',   icon: '👤', desc: 'Kullanıcı oluştur, düzenle, rol ata' },
		{ href: '/obs/admin/rol-yonetimi',       title: 'Rol Yönetimi',          icon: '🔑', desc: 'Permission atama ve kaldırma'        },
		{ href: '/obs/admin/bolum-yonetimi',     title: 'Bölüm Yönetimi',        icon: '🏛️', desc: 'Fakülte ve bölüm tanımları'          },
		{ href: '/obs/admin/donem-yonetimi',     title: 'Dönem Yönetimi',        icon: '📅', desc: 'Dönem açma, aktif yapma'             },
		{ href: '/obs/admin/ders-katalogu',      title: 'Ders Kataloğu',         icon: '📚', desc: 'Ders tanımı ve kataloğu'             },
		{ href: '/obs/admin/sube-acma',          title: 'Şube Açma',             icon: '🗂️', desc: 'Akademisyen atama, kontenjan'        },
		{ href: '/obs/admin/derslik-yonetimi',   title: 'Derslik Yönetimi',      icon: '🏫', desc: 'Fiziksel ve online derslikler'       },
		{ href: '/obs/admin/akademik-takvim',    title: 'Akademik Takvim',       icon: '🗓️', desc: 'Not girişi, yoklama pencereleri'     },
		{ href: '/obs/admin/kayit-kurallari',    title: 'Kayıt Kuralları',       icon: '⚙️', desc: 'AKTS limit, GPA eşiği, deadline'    },
		{ href: '/obs/admin/belge-talebi-isleme',title: 'Belge Talebi İşleme',  icon: '📄', desc: 'Bekleyen talepleri tamamla'          },
		{ href: '/obs/admin/duyuru-global',      title: 'Global Duyuru',         icon: '📢', desc: 'Tüm kullanıcılara duyuru'            },
		{ href: '/obs/admin/audit-kayitlari',    title: 'Audit Kayıtları',       icon: '🔍', desc: 'İşlem geçmişi ve loglama'            },
	];
</script>

<svelte:head><title>OBS — Admin Paneli</title></svelte:head>

<ObsShell activePath="/obs/admin" role="admin" termLabel="2025-2026 Bahar">
	<span slot="userline">{$user?.name ?? 'Admin'} • Admin Paneli</span>

	{#if statsErr}
		<div class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">{statsErr}</div>
	{/if}

	<!-- İstatistik kartlar -->
	<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
		{#each [
			{ label: 'Toplam Kullanıcı',  value: stats?.users_total ?? (loading ? '…' : '—'),    color: 'sky'     },
			{ label: 'Aktif Kullanıcı',   value: stats?.users_active ?? (loading ? '…' : '—'),   color: 'emerald' },
			{ label: 'Açık Şube',         value: stats?.sections ?? (loading ? '…' : '—'),        color: 'violet'  },
			{ label: 'Ders (Katalog)',     value: stats?.courses ?? (loading ? '…' : '—'),         color: 'amber'   },
		] as card}
			<div class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">{card.label}</div>
				<div class="mt-1.5 text-2xl font-black text-slate-800 dark:text-slate-100">{card.value}</div>
			</div>
		{/each}
	</div>

	<!-- Modüller -->
	<div class="mt-5">
		<div class="mb-3 text-xs font-bold tracking-widest text-slate-400 dark:text-slate-500">YÖNETİM MODÜLLERİ</div>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each modules as m}
				<a href={m.href}
					class="group flex items-start gap-3 rounded-xl border border-black/10 bg-white p-4 shadow-sm transition hover:-translate-y-px hover:shadow-md dark:border-white/10 dark:bg-white/5">
					<span class="text-2xl leading-none">{m.icon}</span>
					<div class="min-w-0">
						<div class="text-sm font-semibold group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors">{m.title}</div>
						<div class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{m.desc}</div>
					</div>
				</a>
			{/each}
		</div>
	</div>
</ObsShell>
