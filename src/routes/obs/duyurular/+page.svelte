<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS • Duyurular</title>
</svelte:head>

<ObsShell activePath="/obs/duyurular">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">Duyurular</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			API bağlanınca duyuruları burada listeleyeceğiz.
		</div>

		<div class="mt-4 space-y-3">
			<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
				<div class="text-sm font-semibold">Örnek Duyuru Başlığı</div>
				<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
					Örnek içerik. Tarih • Kaynak bilgisi burada olacak.
				</div>
			</div>
		</div>
	</div>
</ObsShell>

