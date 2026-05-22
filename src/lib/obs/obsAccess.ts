import { devGetObsRole } from '$lib/apis/douAcademic';

/** Auth sayfasında seçilen OBS portalı (giriş türü ile sunucu rolü eşleşmesi için). */
export const OBS_PORTAL_ROLE_PICK_KEY = 'obsPortalRolePick';

export type ObsArea = 'ogrenci' | 'akademisyen' | 'admin';

/** Sunucudaki obs_role / Open WebUI rolünden panel alanını üretir. */
export function normalizeObsArea(
	raw: string | undefined | null,
	openWebUiRole?: string | null
): ObsArea {
	const or = (openWebUiRole ?? '').trim().toLowerCase();
	if (or === 'admin') return 'admin';
	if (or === 'academician') return 'akademisyen';
	const r = (raw ?? '').trim().toLowerCase();
	if (r === 'admin') return 'admin';
	if (r === 'akademisyen' || r === 'academician') return 'akademisyen';
	return 'ogrenci';
}

export function obsAreaHome(area: ObsArea): string {
	switch (area) {
		case 'admin':
			return '/obs/admin';
		case 'akademisyen':
			return '/obs/akademisyen';
		default:
			return '/obs/ogrenci';
	}
}

export async function resolveObsArea(
	token: string | null,
	openWebUiRole?: string | null
): Promise<ObsArea> {
	if (!token) return normalizeObsArea(null, openWebUiRole);
	try {
		const res = await devGetObsRole(token);
		return normalizeObsArea(res.obs_role, openWebUiRole);
	} catch {
		return normalizeObsArea(null, openWebUiRole);
	}
}

/** Sunucu rolüne göre alan; yerel rol override kullanılmaz. */
export async function resolveObsAreaWithDevOverride(
	token: string | null,
	openWebUiRole?: string | null
): Promise<ObsArea> {
	return resolveObsArea(token, openWebUiRole);
}
