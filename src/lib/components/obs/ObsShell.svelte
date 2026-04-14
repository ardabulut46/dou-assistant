<script lang="ts">
	export let title = 'Öğrenci Bilgi Sistemi';
	export let subtitle = 'Doğuş Üniversitesi';
	export let termLabel = '2025-2026 Bahar';

	export let activePath: string = '/obs';

	type NavItem = {
		label: string;
		href: string;
		section?: string;
		disabled?: boolean;
	};

	type InputGroup = {
		title: string;
		items: string[];
	};

	type NavGroup = {
		label: string;
		section?: string;
		items: NavItem[];
		baseHref?: string; // collapsible root
	};

	// Accordion: sadece 1 grup açık kalsın
	let openGroup: string = '/obs/genel-islemler';

	const isActive = (href: string) => activePath === href;
	const isIn = (base: string) => activePath === base || activePath.startsWith(`${base}/`);

	const inputGroups: InputGroup[] = [
		{
			title: 'Genel İşlemler',
			items: [
				'Kullanım Kılavuzu',
				'Özlük Bilgileri',
				'Genel Bilgiler',
				'Akademik Takvim',
				'Danışman Bilgileri',
				'Alınan Dersler',
				'Açılan Bölüm Dersleri',
				'Sınav Takvimi',
				'Ders Programı',
				'Harç Bilgileri',
				'Staj Bilgileri',
				'Genel Duyurular',
				'Mezuniyet Onay Bilgileri'
			]
		},
		{
			title: 'Ders ve Dönem İşlemleri',
			items: [
				'Ders Kayıt',
				'Ders Ekle/Bırak',
				'Dönem Ortalamaları',
				'Not Listesi',
				'Transkript',
				'Transkript Senaryosu',
				'Diğer Belgeler',
				'Müfredat Durum',
				'Müfredat Bilgi Paketi',
				'Staj Başvurusu',
				'Devamsızlık Durumu'
			]
		},
		{ title: 'Form İşlemleri', items: ['Anketler', 'Değerlendirme Formları', 'Hazırlık Değer. Formları', 'Öğrenci Bilgi Formu'] },
		{ title: 'İntibak Başvuru', items: ['İntibak Başvuru'] },
		{
			title: 'Sosyal Transkript İşlemleri',
			items: [
				'İstatistikler',
				'Etkinlik Başvuru',
				'Etkinliklerim',
				'Kayıtlı Belgelerim',
				'Etkinlik Kategorileri',
				'Sıkça Sorulan Sorular'
			]
		},
		{
			title: 'Hazırlık İşlemleri',
			items: ['Haz. Sınav Takvimi', 'Haz. Not Listesi', 'Haz. Devamsızlık Durumu', 'Hazırlık Ders Programı']
		},
		{
			title: 'Başvuru İşlemleri',
			items: [
				'Değişim Prog. Başvuru İşlemleri V2',
				'Tek Ders Başvuru',
				'Ek Sınav Başvuru',
				'ÇAP Başvuru',
				'Yandal Başvuru',
				'Kayıt Dondurma Başvuru',
				'Mazeret Sınavı Başvuru',
				'Ek Sınav Başvuru V2',
				'Ek Sınav Başvuru İşlemleri',
				'Tek Ders Başvuru İşlemleri'
			]
		},
		{ title: 'Staj İşlemleri', items: ['Öğrenci Staj İşlemleri'] },
		{
			title: 'Kullanıcı İşlemleri',
			items: ['Yapılacaklar Listesi', 'Gelen Mesajlar', 'Gönderilen Mesajlar', 'Belge Talebi', 'Şifre Değiştir', 'Fotoğraf Güncelle']
		}
	];

	const toSlug = (s: string) =>
		s
			.trim()
			.toLowerCase()
			.replaceAll('ç', 'c')
			.replaceAll('ğ', 'g')
			.replaceAll('ı', 'i')
			.replaceAll('i̇', 'i')
			.replaceAll('ö', 'o')
			.replaceAll('ş', 's')
			.replaceAll('ü', 'u')
			.replaceAll('.', '')
			.replaceAll('/', '-')
			.replaceAll('(', '')
			.replaceAll(')', '')
			.replaceAll(':', '')
			.replaceAll(',', '')
			.replace(/\s+/g, '-')
			.replace(/-+/g, '-');

	const groupBase: Record<string, string> = {
		'Genel İşlemler': '/obs/genel',
		'Ders ve Dönem İşlemleri': '/obs/ders-donem',
		'Form İşlemleri': '/obs/form',
		'İntibak Başvuru': '/obs/intibak',
		'Sosyal Transkript İşlemleri': '/obs/sosyal-transkript',
		'Hazırlık İşlemleri': '/obs/hazirlik',
		'Başvuru İşlemleri': '/obs/basvuru',
		'Staj İşlemleri': '/obs/staj',
		'Kullanıcı İşlemleri': '/obs/kullanici'
	};

	const groups: NavGroup[] = inputGroups.map((g) => {
		const baseHref = groupBase[g.title] ?? `/obs/${toSlug(g.title)}`;
		return {
			section: g.title.toUpperCase(),
			label: g.title,
			baseHref,
			items: g.items.map((label) => ({ label, href: `${baseHref}/${toSlug(label)}` }))
		};
	});
</script>

<div class="min-h-[100dvh] bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
	<div class="flex min-h-[100dvh]">
		<aside class="w-[320px] shrink-0 bg-slate-950 text-slate-100">
			<div class="sticky top-0 z-10 bg-slate-950 px-5 py-5">
				<div class="flex items-center gap-3">
					<div class="size-12 rounded-full bg-white/10 ring-1 ring-white/15" />
					<div class="min-w-0">
						<div class="truncate text-sm font-semibold">{subtitle}</div>
						<div class="truncate text-xs text-slate-300">{title}</div>
					</div>
				</div>
			</div>

			<nav class="h-[calc(100dvh-88px)] overflow-y-auto px-3 pb-8">
				{#each groups as group (group.label)}
					{#if group.section}
						<div class="px-3 pb-2 pt-3 text-[11px] font-semibold tracking-widest text-slate-400">
							{group.section}
						</div>
					{/if}

					{#if group.baseHref}
						<button
							class="mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm font-medium transition hover:bg-white/10 {isIn(
								group.baseHref
							)
								? 'bg-white/10 ring-1 ring-white/10'
								: ''}"
							on:click={() => {
								const key = group.baseHref;
								openGroup = openGroup === key ? '' : key;
							}}
						>
							<span class="min-w-0 truncate">{group.label}</span>
							<span class="text-slate-400">{openGroup === group.baseHref ? '▾' : '▸'}</span>
						</button>

						{#if openGroup === group.baseHref}
							<div class="space-y-1 pl-2">
								{#each group.items as item}
									<a
										href={item.href}
										aria-current={isActive(item.href) ? 'page' : undefined}
										class="group flex w-full items-center justify-between rounded-xl px-3 py-2 text-[13px] leading-5 transition
										{isActive(item.href)
											? 'bg-white/12 ring-1 ring-white/10'
											: 'hover:bg-white/10'}
										{item.disabled ? 'pointer-events-none opacity-50' : ''}"
									>
										<span class="min-w-0 truncate">{item.label}</span>
										<span class="text-slate-400 opacity-0 transition group-hover:opacity-60 {isActive(item.href)
											? 'opacity-60'
											: ''}"
											>›</span
										>
									</a>
								{/each}
							</div>
						{/if}
					{:else}
						<div class="space-y-1">
							{#each group.items as item}
								<a
									href={item.href}
									aria-current={isActive(item.href) ? 'page' : undefined}
									class="group flex w-full items-center justify-between rounded-xl px-3 py-2 text-[13px] leading-5 transition
									{isActive(item.href)
										? 'bg-white/12 ring-1 ring-white/10'
										: 'hover:bg-white/10'}
									{item.disabled ? 'pointer-events-none opacity-50' : ''}"
								>
									<span class="min-w-0 truncate">{item.label}</span>
									<span class="text-slate-400 opacity-0 transition group-hover:opacity-60 {isActive(item.href)
										? 'opacity-60'
										: ''}"
										>›</span
									>
								</a>
							{/each}
						</div>
					{/if}
				{/each}
			</nav>
		</aside>

		<div class="min-w-0 flex-1">
			<header
				class="sticky top-0 z-10 border-b border-black/10 bg-white/80 px-6 py-3 backdrop-blur dark:border-white/10 dark:bg-slate-950/70"
			>
				<div class="flex items-center justify-between gap-4">
					<div class="min-w-0">
						<div class="truncate text-sm font-semibold">{termLabel}</div>
						<div class="truncate text-xs text-slate-500 dark:text-slate-400">
							<slot name="userline" />
						</div>
					</div>
					<div class="flex shrink-0 items-center gap-2">
						<a
							href="/"
							class="rounded-xl bg-sky-500 px-3 py-2 text-sm font-semibold text-white hover:bg-sky-400"
						>
							AI’a Sor
						</a>
						<a
							href="/"
							class="rounded-xl border border-black/10 bg-white px-3 py-2 text-sm hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
						>
							AI Asistan
						</a>
						<slot name="actions" />
					</div>
				</div>
			</header>

			<main class="px-6 py-5">
				<slot />
			</main>
		</div>
	</div>
</div>

