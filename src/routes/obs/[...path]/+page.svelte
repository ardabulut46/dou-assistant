<script lang="ts">
	import { page } from '$app/stores';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';

	const labels: Record<string, { title: string; hint?: string; variant?: string }> = {
		'/obs/genel/kullanim-kilavuzu': {
			title: 'Kullanım Kılavuzu',
			hint: 'Kısa ipuçları ve sık sorulanlar (demo).',
			variant: 'list'
		},
		'/obs/genel/akademik-takvim': { title: 'Akademik Takvim', hint: 'Tarihler (demo).', variant: 'table' },
		'/obs/genel/danisman-bilgileri': { title: 'Danışman Bilgileri', hint: 'Danışman detayları (demo).' },
		'/obs/genel/sinav-takvimi': { title: 'Sınav Takvimi', hint: 'Sınav listesi (demo).', variant: 'table' },
		'/obs/genel/ders-programi': { title: 'Ders Programı', hint: 'Haftalık program (demo).', variant: 'table' },
		'/obs/genel/harc-bilgileri': { title: 'Harç Bilgileri', hint: 'Ödeme/borç bilgileri (demo).', variant: 'table' },
		'/obs/genel/staj-bilgileri': { title: 'Staj Bilgileri', hint: 'Staj durum özeti (demo).', variant: 'list' },
		'/obs/genel/genel-duyurular': { title: 'Genel Duyurular', hint: 'Duyuru akışı (demo).', variant: 'cards' },
		'/obs/genel/mezuniyet-onay': { title: 'Mezuniyet Onay Bilgileri', hint: 'Kontrol listesi (demo).' },

		'/obs/ders-donem/ders-kayit': { title: 'Ders Kayıt', hint: 'Ders kayıt işlemi (demo).', variant: 'form' },
		'/obs/ders-donem/ders-ekle-birak': { title: 'Ders Ekle/Bırak', hint: 'Ekle/bırak (demo).', variant: 'table' },
		'/obs/ders-donem/donem-ortalamalari': { title: 'Dönem Ortalamaları', hint: 'Ortalamalar (demo).', variant: 'table' },
		'/obs/ders-donem/not-listesi': { title: 'Not Listesi', hint: 'Ders notları (demo).', variant: 'table' },
		'/obs/ders-donem/transkript': { title: 'Transkript', hint: 'Transkript (demo).', variant: 'table' },
		'/obs/ders-donem/transkript-senaryosu': { title: 'Transkript Senaryosu', hint: 'Senaryo seçimi (demo).' },
		'/obs/ders-donem/diger-belgeler': { title: 'Diğer Belgeler', hint: 'Belge listesi (demo).', variant: 'list' },
		'/obs/ders-donem/mufredat-durum': { title: 'Müfredat Durum', hint: 'Müfredat durum (demo).', variant: 'table' },
		'/obs/ders-donem/mufredat-bilgi-paketi': { title: 'Müfredat Bilgi Paketi', hint: 'Bilgi paketi (demo).' },
		'/obs/ders-donem/sinav-basvurusu': { title: 'Sınav Başvurusu', hint: 'Başvuru formu (demo).', variant: 'form' },
		'/obs/ders-donem/devamsizlik-durumu': { title: 'Devamsızlık Durumu', hint: 'Devamsızlık (demo).', variant: 'table' },

		'/obs/form/anketler': { title: 'Anketler', hint: 'Anket listesi (demo).', variant: 'list' },
		'/obs/form/degerlendirme-formlari': {
			title: 'Değerlendirme Formları',
			hint: 'Form listesi (demo).',
			variant: 'list'
		},
		'/obs/form/hazirlik-deger-formlari': {
			title: 'Hazırlık Değer. Formları',
			hint: 'Hazırlık formları (demo).',
			variant: 'list'
		},
		'/obs/form/ogrenci-bilgi-formu': { title: 'Öğrenci Bilgi Formu', hint: 'Bilgi formu (demo).', variant: 'form' },

		'/obs/hazirlik/sinav-takvimi': { title: 'Haz. Sınav Takvimi', hint: 'Hazırlık sınavları (demo).', variant: 'table' },
		'/obs/hazirlik/not-listesi': { title: 'Haz. Not Listesi', hint: 'Hazırlık notları (demo).', variant: 'table' },
		'/obs/hazirlik/devamsizlik-durumu': { title: 'Haz. Devamsızlık Durumu', hint: 'Devamsızlık (demo).', variant: 'table' },
		'/obs/hazirlik/ders-programi': { title: 'Hazırlık Ders Programı', hint: 'Program (demo).', variant: 'table' },

		'/obs/basvuru/degisim-prog-v2': { title: 'Değişim Programı Başvurusu (V2)', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/tek-ders': { title: 'Tek Ders Başvuru', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/ek-sinav': { title: 'Ek Sınav Başvuru', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/cap': { title: 'ÇAP Başvuru', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/yandal': { title: 'Yandal Başvuru', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/kayit-dondurma': { title: 'Kayıt Dondurma Başvuru', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/mazeret-sinavi': { title: 'Mazeret Sınavı Başvuru', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/ek-sinav-v2': { title: 'Ek Sınav Başvuru (V2)', hint: 'Başvuru (demo).', variant: 'form' },
		'/obs/basvuru/ek-sinav-islemleri': { title: 'Ek Sınav Başvuru İşlemleri', hint: 'İşlemler (demo).', variant: 'list' },
		'/obs/basvuru/tek-ders-islemleri': { title: 'Tek Ders Başvuru İşlemleri', hint: 'İşlemler (demo).', variant: 'list' },

		'/obs/staj/ogrenci-staj': { title: 'Öğrenci Staj İşlemleri', hint: 'Staj işlemleri (demo).', variant: 'form' },

		'/obs/kullanici/yapilacaklar': { title: 'Yapılacaklar Listesi', hint: 'Todo (demo).', variant: 'list' },
		'/obs/kullanici/gelen-mesajlar': { title: 'Gelen Mesajlar', hint: 'Inbox (demo).', variant: 'list' },
		'/obs/kullanici/gonderilen-mesajlar': { title: 'Gönderilen Mesajlar', hint: 'Outbox (demo).', variant: 'list' },
		'/obs/kullanici/belge-talebi': { title: 'Belge Talebi', hint: 'Belge talebi (demo).', variant: 'form' },
		'/obs/kullanici/sifre-degistir': { title: 'Şifre Değiştir', hint: 'Şifre değiştir (demo).', variant: 'form' },
		'/obs/kullanici/fotograf-guncelle': { title: 'Fotoğraf Güncelle', hint: 'Profil foto (demo).', variant: 'form' }
	};

	$: rest = $page.params.path || '';
	$: activePath = `/obs/${rest}`;
	const prettify = (s: string) =>
		decodeURIComponent(s)
			.split('/')
			.filter(Boolean)
			.at(-1)
			?.replaceAll('-', ' ')
			?.replace(/\b\w/g, (c) => c.toUpperCase()) ?? 'OBS';

	$: meta = labels[activePath] ?? { title: rest ? prettify(rest) : 'OBS', hint: 'Demo içerik.' };
	$: title = meta.title;
	$: hint = meta.hint ?? 'Demo içerik.';
	$: variant = meta.variant ?? 'default';
</script>

<svelte:head>
	<title>OBS • {title}</title>
</svelte:head>

<ObsShell {activePath}>
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">{title}</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">{hint}</div>

		{#if variant === 'table'}
			<div class="mt-4 overflow-hidden rounded-xl border border-black/10 dark:border-white/10">
				<div
					class="grid grid-cols-4 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-600 dark:bg-white/5 dark:text-slate-300"
				>
					<div>Alan</div>
					<div>Değer</div>
					<div>Durum</div>
					<div>Not</div>
				</div>
				<div class="grid grid-cols-4 px-4 py-3 text-sm">
					<div>Örnek</div>
					<div>—</div>
					<div>—</div>
					<div>Demo</div>
				</div>
			</div>
		{:else if variant === 'form'}
			<div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
				<label class="block">
					<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Başlık</div>
					<input
						class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
						placeholder="Demo"
					/>
				</label>
				<label class="block">
					<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Seçim</div>
					<select
						class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
					>
						<option>Seçenek 1</option>
						<option>Seçenek 2</option>
					</select>
				</label>
				<label class="block lg:col-span-2">
					<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Açıklama</div>
					<textarea
						class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
						rows="3"
						placeholder="Demo açıklama"
					/>
				</label>
				<div class="lg:col-span-2">
					<button
						type="button"
						class="rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400"
					>
						Gönder (demo)
					</button>
				</div>
			</div>
		{:else if variant === 'cards'}
			<div class="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
				<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
					<div class="text-sm font-semibold">Örnek Duyuru</div>
					<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">Tarih • Kaynak</div>
				</div>
				<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
					<div class="text-sm font-semibold">Örnek Duyuru 2</div>
					<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">Tarih • Kaynak</div>
				</div>
			</div>
		{:else}
			<div class="mt-4 rounded-xl border border-dashed border-black/15 bg-slate-50 p-4 text-sm text-slate-600 dark:border-white/15 dark:bg-white/5 dark:text-slate-300">
				Bu sayfa demo. API bağlanınca gerçek içerik gelecek.
			</div>
		{/if}
	</div>
</ObsShell>

