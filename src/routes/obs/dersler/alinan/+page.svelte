<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS • Alınan Dersler</title>
</svelte:head>

<ObsShell activePath="/obs/dersler/alinan">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">Alınan Dersler</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			Kafadan örnek tablo. Sonra GET ile dolduracağız.
		</div>

		<div class="mt-4 overflow-hidden rounded-xl border border-black/10 dark:border-white/10">
			<div class="grid grid-cols-6 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-600 dark:bg-white/5 dark:text-slate-300">
				<div>Ders Kodu</div>
				<div class="col-span-2">Ders Adı</div>
				<div>AKTS</div>
				<div>Şube</div>
				<div>Öğrt. Elemanı</div>
			</div>
			<div class="grid grid-cols-6 px-4 py-3 text-sm">
				<div>YBS 492</div>
				<div class="col-span-2">Bitirme Projesi</div>
				<div>7</div>
				<div>1</div>
				<div class="truncate">Arş. Gör. ...</div>
			</div>
		</div>
	</div>
</ObsShell>

