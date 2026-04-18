<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Chat from '$lib/components/chat/Chat.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

	let lastObsPath: string | null = null;

	onMount(() => {
		if ($page.url.searchParams.get('error')) {
			toast.error($page.url.searchParams.get('error') || 'An unknown error occurred.');
		}

		try {
			lastObsPath = localStorage.getItem('obs:lastPath');
		} catch {
			lastObsPath = null;
		}
	});

	$: back = $page.url.searchParams.get('back');
</script>

{#if back || lastObsPath}
	<!-- Keep top placement but avoid overlapping top-right menus -->
	<div class="fixed top-16 right-4 z-50">
		<button
			class="rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white shadow-lg hover:bg-slate-800"
			on:click={() => goto(back || lastObsPath)}
		>
			OBS’ye dön
		</button>
	</div>
{/if}

<Chat />
