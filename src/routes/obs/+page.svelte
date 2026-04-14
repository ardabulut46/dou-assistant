<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS</title>
</svelte:head>

<ObsShell activePath="/obs">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div
		class="mb-5 rounded-2xl border border-emerald-900/10 bg-emerald-600 px-4 py-3 text-sm text-white shadow-sm"
	>
		<span class="font-semibold">Bilgilendirme:</span>
		2025-2026 Bahar döneminde 5 adet onaylanmış ders kaydınız mevcut.
	</div>

	<div class="grid grid-cols-1 gap-4 lg:grid-cols-4">
		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">
				Aktif Akademik Dönem Bilgileri
			</div>
			<div class="mt-1 text-sm font-semibold">2025-2026 Bahar</div>
			<div class="mt-3">
				<span
					class="rounded-xl bg-slate-900/5 px-2 py-1 text-xs text-slate-600 dark:bg-white/10 dark:text-slate-200"
					>Aktif</span
				>
			</div>
		</div>

		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Danışman Bilgileri</div>
			<div class="mt-1 text-sm font-semibold">Dan. Öğr. Üyesi</div>
			<div class="mt-2 text-xs text-slate-500 dark:text-slate-300">
				E-posta: <span class="font-medium">advisor@dogus.edu.tr</span>
			</div>
		</div>

		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Öğrenci Bilgileri</div>
			<div class="mt-1 text-sm font-semibold">İletişim / Kayıt</div>
			<div class="mt-2 text-xs text-slate-500 dark:text-slate-300">
				Kişisel bilgiler ve iletişim ayarları
			</div>
		</div>

		<div class="rounded-2xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
			<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Kayıt Tarihi</div>
			<div class="mt-1 text-sm font-semibold">Örn: 05.09.2021</div>
			<div class="mt-2 text-xs text-slate-500 dark:text-slate-300">A.GNO: 3.26</div>
		</div>
	</div>

	<div class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
		<a
			href="/obs/dersler"
			class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm transition hover:-translate-y-[1px] hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
		>
			<div class="text-sm font-semibold">Dersler</div>
			<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
				Ders listesi ve dönem işlemleri
			</div>
		</a>

		<a
			href="/obs/notlar"
			class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm transition hover:-translate-y-[1px] hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
		>
			<div class="text-sm font-semibold">Notlar</div>
			<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">Sınav / ödev notları</div>
		</a>

		<a
			href="/obs/duyurular"
			class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm transition hover:-translate-y-[1px] hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
		>
			<div class="text-sm font-semibold">Duyurular</div>
			<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">Bölüm / ders duyuruları</div>
		</a>
	</div>
</ObsShell>

