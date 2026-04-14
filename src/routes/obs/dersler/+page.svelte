<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS • Dersler</title>
</svelte:head>

<ObsShell activePath="/obs/dersler">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">Ders ve Dönem İşlemleri</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			Bu sayfayı API’ye bağlayınca ders listesi burada gözükecek.
		</div>

		<div class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
			<div class="rounded-xl border border-black/10 bg-slate-50 p-4 text-sm dark:border-white/10 dark:bg-white/5">
				<div class="font-semibold">Ders Seçimi</div>
				<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">Ders ekle/bırak</div>
			</div>
			<div class="rounded-xl border border-black/10 bg-slate-50 p-4 text-sm dark:border-white/10 dark:bg-white/5">
				<div class="font-semibold">Ders Programı</div>
				<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">Haftalık program</div>
			</div>
		</div>
	</div>
</ObsShell>

