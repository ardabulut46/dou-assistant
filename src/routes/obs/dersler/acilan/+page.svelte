<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS • Açılan Bölüm Dersleri</title>
</svelte:head>

<ObsShell activePath="/obs/dersler/acilan">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">Açılan Bölüm Dersleri</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			Kafadan örnek liste. Sonra filtre + pagination ekleriz.
		</div>

		<div class="mt-4 overflow-hidden rounded-xl border border-black/10 dark:border-white/10">
			<div class="grid grid-cols-6 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-600 dark:bg-white/5 dark:text-slate-300">
				<div>Şb.</div>
				<div>Ders Kodu</div>
				<div class="col-span-2">Ders Adı</div>
				<div>AKTS</div>
				<div>Kontenjan</div>
			</div>
			<div class="grid grid-cols-6 px-4 py-3 text-sm">
				<div>1</div>
				<div>YBS 314</div>
				<div class="col-span-2">Sistem Analizi ve Tasarım</div>
				<div>6</div>
				<div>0 / 40</div>
			</div>
		</div>
	</div>
</ObsShell>

