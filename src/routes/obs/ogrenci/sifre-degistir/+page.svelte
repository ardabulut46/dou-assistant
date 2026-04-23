<script lang="ts">
	import OgrenciSubpage from '$lib/components/obs/ogrenci/OgrenciSubpage.svelte';
	import { OGRENCI_PAGES, type OgrenciPath } from '$lib/obs/ogrenci/paths';

	const path: OgrenciPath = '/obs/ogrenci/sifre-degistir';
	const meta = OGRENCI_PAGES[path];
</script>

<OgrenciSubpage activePath={path} {meta} />
