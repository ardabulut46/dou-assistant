<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS • Notlar</title>
</svelte:head>

<ObsShell activePath="/obs/notlar">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">Notlar</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			API bağlanınca ders bazlı sınav/ödev notlarını burada göstereceğiz.
		</div>

		<div class="mt-4 overflow-hidden rounded-xl border border-black/10 dark:border-white/10">
			<div class="grid grid-cols-4 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-600 dark:bg-white/5 dark:text-slate-300">
				<div>Ders</div>
				<div>Vize</div>
				<div>Final</div>
				<div>Harf</div>
			</div>
			<div class="grid grid-cols-4 px-4 py-3 text-sm">
				<div class="text-slate-700 dark:text-slate-200">Örnek Ders</div>
				<div>—</div>
				<div>—</div>
				<div>—</div>
			</div>
		</div>
	</div>
</ObsShell>

