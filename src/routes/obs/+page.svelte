<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { user } from '$lib/stores';

	onMount(() => {
		if (!browser) return;

		// Dev/test: localStorage'da rol override varsa onu kullan
		const devRole = localStorage.getItem('obsRoleOverride') ?? '';
		const baseRole = devRole || $user?.role || '';

		if (baseRole === 'Admin' || baseRole === 'admin') {
			goto('/obs/admin', { replaceState: true });
		} else if (
			baseRole === 'Akademisyen' ||
			baseRole === 'akademisyen' ||
			baseRole === 'Academician' ||
			baseRole === 'academician'
		) {
			goto('/obs/akademisyen', { replaceState: true });
		} else {
			// Öğrenci, user, boş veya bilinmeyen → öğrenci paneline
			goto('/obs/ogrenci', { replaceState: true });
		}
	});
</script>

<div class="flex min-h-screen items-center justify-center bg-slate-100 dark:bg-slate-950">
	<div class="text-sm text-slate-400">Yönlendiriliyor…</div>
</div>
