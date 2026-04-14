<script lang="ts">
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
</script>

<svelte:head>
	<title>OBS • İletişim Bilgileri</title>
</svelte:head>

<ObsShell activePath="/obs/ozluk/iletisim">
	<span slot="userline">Ramazan • Kullanıcı</span>

	<div class="rounded-2xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
		<div class="text-sm font-semibold">İletişim Bilgileri</div>
		<div class="mt-1 text-xs text-slate-500 dark:text-slate-300">
			Şimdilik basic form. Sonra PUT ile güncelleriz.
		</div>

		<div class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
			<label class="block">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">E-posta</div>
				<input
					class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
					value="ramazan.bakan@example.com"
					readonly
				/>
			</label>

			<label class="block">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Telefon</div>
				<input
					class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
					value="(5xx) xxx xx xx"
				/>
			</label>

			<label class="block lg:col-span-2">
				<div class="text-xs font-semibold text-slate-500 dark:text-slate-300">Adres</div>
				<textarea
					class="mt-1 w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-white/5"
					rows="3"
				>İstanbul / Türkiye</textarea>
			</label>

			<div class="lg:col-span-2">
				<button
					type="button"
					class="rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400"
				>
					Kaydet (demo)
				</button>
			</div>
		</div>
	</div>
</ObsShell>

