<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS • Genel Bilgiler</title>
</svelte:head>

<ObsShell activePath="/obs/ozluk/genel">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">Genel Bilgiler</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			Şimdilik kafadan basic veriler. API bağlanınca gerçek veriler gelecek.
		</div>

		<div class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
			<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Öğrenci No</div>
				<div class="mt-1 text-sm font-semibold">2021020XXXXX</div>
			</div>
			<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Program</div>
				<div class="mt-1 text-sm font-semibold">Yönetim Bilişim Sistemleri</div>
			</div>
			<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Sınıf</div>
				<div class="mt-1 text-sm font-semibold">4</div>
			</div>
			<div class="rounded-xl border border-black/10 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">A.GNO</div>
				<div class="mt-1 text-sm font-semibold">3.26</div>
			</div>
		</div>
	</div>
</ObsShell>

