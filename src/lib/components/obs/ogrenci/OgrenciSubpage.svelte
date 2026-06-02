<script lang="ts">
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { tick } from 'svelte';
	import { user } from '$lib/stores';
	import type { OgrenciPageMeta, OgrenciPath } from '$lib/obs/ogrenci/paths';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { searchKnowledgeBases, searchKnowledgeFilesById } from '$lib/apis/knowledge';

	export let activePath: OgrenciPath;
	export let meta: OgrenciPageMeta;
	import {
		getDouTerms,
		getDouStudentProfile,
		getDouStudentAdvisor,
		getDouStudentRegistrationLimits,
		getDouStudentEnrollments,
		getDouStudentGrades,
		getDouStudentGpaSummary,
		getDouStudentTranscript,
		getDouStudentAttendance,
		getDouStudentExams,
		getDouStudentSchedule,
		getDouStudentAnnouncements,
		getDouInbox,
		getDouSent,
		getDouStudentDocumentRequests,
		createDouDocumentRequest,
		updateDouStudentProfile,
		getDouAvailableCourses,
		postDouDraftEnrollments,
		deleteDouDraftEnrollment,
		submitDouStudentSchedule,
		sendDouMessageApi,
		getDouCurriculumStatus,
		type DouTerm,
		type DouStudentProfile,
		type DouAdvisorResponse,
		type DouStudentRegistrationLimits,
		type DouEnrollment,
		type DouGradeEntry,
		type DouAttendanceRow,
		type DouExam,
		type DouScheduleRow,
		type DouAnnouncement,
		type DouMessage,
		type DouDocumentRequest,
		type AvailableCourse,
		type DouAvailableCoursesResponse,
		type CoursesPendingSectionsBrief,
		type CurriculumMandatoryBrief
	} from '$lib/apis/douAcademic';

	$: pageTitle = meta?.title ?? 'OBS';
	$: apiKey = meta?.apiKey ?? '';

	// ---------------------------------------------------------------------------
	// State değişkenleri
	// ---------------------------------------------------------------------------
	let loading = false;
	let loadErr: string | null = null;

	// veritipleri
	let profile: DouStudentProfile | null = null;
	let terms: DouTerm[] = [];
	let calendarDocs: Array<{ id: string; filename: string; meta?: Record<string, unknown>; size?: number }> =
		[];
	let advisor: DouAdvisorResponse | null = null;
	let enrollments: DouEnrollment[] = [];
	let totalAkts = 0;
	let grades: DouGradeEntry[] = [];
	let gpaTerms: unknown[] = [];
	let cumulativeGpa: number | null = null;
	let transcript: unknown[] | null = null;
	let transcriptTotalAkts: number | null = null;
	let attendance: DouAttendanceRow[] = [];
	/** Devamsızlık sekmesi: API `term_id` filtresi */
	let selectedAttendanceTermId = '';
	/** Not listesi: seçilen akademik dönem */
	let selectedGradesTermId = '';
	/** Ders programı sekmesi: API `term_id` filtresi */
	let selectedScheduleTermId = '';

	const ACADEMIC_CAL_KB_NAME = 'Akademik Takvim';

	async function resolveAcademicCalendarKbId(token: string): Promise<string | null> {
		const res = await searchKnowledgeBases(token, ACADEMIC_CAL_KB_NAME, null, 1).catch(() => null);
		const items = (res?.items ?? res?.knowledges ?? res?.knowledge_bases ?? []) as Array<{
			id: string;
			name?: string;
		}>;
		const exact = items.find((k) => (k?.name ?? '').trim() === ACADEMIC_CAL_KB_NAME);
		return exact?.id ?? null;
	}

	function fileTermId(file: { meta?: Record<string, unknown> } | null | undefined): string {
		const m = (file?.meta ?? {}) as Record<string, unknown>;
		return String((m.term_id ?? m.calendar_term_id ?? '') as string);
	}

	function fmtBytes(n: number | null | undefined) {
		const v = Number(n ?? 0);
		if (!Number.isFinite(v) || v <= 0) return '';
		const units = ['B', 'KB', 'MB', 'GB'];
		let idx = 0;
		let val = v;
		while (val >= 1024 && idx < units.length - 1) {
			val /= 1024;
			idx += 1;
		}
		return `${val.toFixed(val >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
	}

	async function reloadCalendarDocs() {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;

		const kbId = await resolveAcademicCalendarKbId(token);
		if (!kbId) {
			calendarDocs = [];
			return;
		}

		const filesRes = await searchKnowledgeFilesById(token, kbId, null, null, 'updated_at', 'desc', 1).catch(
			() => null
		);
		const items = (filesRes?.items ?? filesRes?.files ?? []) as Array<{
			id: string;
			filename: string;
			meta?: Record<string, unknown>;
			size?: number;
		}>;

		// Öğrenci ekranında sadece PDF listesi gösterilir.
		// Dönem filtresi zorunlu değil; meta.term_id varsa admin tarafında dönem bazlı yüklenebilir.
		calendarDocs = items.map((f) => ({ id: f.id, filename: f.filename, meta: f.meta, size: f.size }));
	}

	function floorPct30Quota(weeks: number): number {
		return weeks > 0 ? Math.floor(weeks * 0.3 + 1e-9) : 0;
	}

	function attendancePctBarClasses(attendancePct: number, kotaFazlası: number): { pct: string; bar: string } {
		if (attendancePct < 70 || kotaFazlası >= 2) {
			return {
				pct: 'text-red-600 dark:text-red-400',
				bar: 'bg-red-600'
			};
		}
		if (kotaFazlası >= 1) {
			return {
				pct: 'text-rose-600 dark:text-rose-400',
				bar: 'bg-rose-500'
			};
		}
		return {
			pct: 'text-emerald-600 dark:text-emerald-400',
			bar: 'bg-emerald-500'
		};
	}

	function absentCellClass(attendancePct: number, kotaFazlası: number): string {
		if (attendancePct < 70 || kotaFazlası >= 2) {
			return 'text-red-600 dark:text-red-400';
		}
		if (kotaFazlası >= 1) return 'text-rose-600 dark:text-rose-400';
		return '';
	}
	let exams: DouExam[] = [];
	let schedule: DouScheduleRow[] = [];
	let announcements: DouAnnouncement[] = [];
	let inboxMsgs: DouMessage[] = [];
	let sentMsgs: DouMessage[] = [];
	let docRequests: DouDocumentRequest[] = [];
	let availableCourses: AvailableCourse[] = [];
	/** Ekle-bırak liste boşken API teşhis alanları. */
	let addDropSectionsEmptyHint = '';
	let addDropSectionsInTermTotal: number | null = null;
	let addDropSectionsQueryRowsStudent: number | null = null;
	let addDropCoursesPendingSections: CoursesPendingSectionsBrief[] = [];
	let addDropRealSectionRowCount = 0;
	let addDropOfferPlaceholderRowsMeta = 0;
	/** Ders kayıt — /available-courses teşhis + ipucu (ekle-bırak alanlarından ayrı). */
	let registrationSectionsEmptyHint = '';
	let registrationSectionsInTermTotal: number | null = null;
	let registrationSectionsQueryRowsStudent: number | null = null;
	let registrationRealSectionRowCount = 0;
	let registrationOfferPlaceholderRowsMeta = 0;

	/** Tür aksanı için ``seçmeli``/``zorunlu`` eşlemesi (DB metinleri). */
	function foldCourseTypeTr(s: string): string {
		return s
			.normalize('NFKC')
			.trim()
			.toLowerCase()
			.replace(/\s+/g, '_')
			.replace(/ğ/g, 'g')
			.replace(/ü/g, 'u')
			.replace(/ş/g, 's')
			.replace(/ı/g, 'i')
			.replace(/ö/g, 'o')
			.replace(/ç/g, 'c');
	}

	/** Ders kartı kayıtta zorunlu mu (API ``is_mandatory_course`` ile ``type`` birlikte). */
	function douCourseIsMandatory(
		row:
			| Pick<DouEnrollment, 'type' | 'is_mandatory_course'>
			| Pick<AvailableCourse, 'type' | 'is_mandatory_course'>
	): boolean {
		const imb = row.is_mandatory_course as unknown;
		const raw = foldCourseTypeTr(String(row.type ?? ''));
		const typeMandatory =
			!!raw &&
			(raw === 'z' ||
				raw === 'zorunlu' ||
				raw === 'required' ||
				raw === 'mandatory' ||
				raw.startsWith('zorunlu'));
		const typeElective =
			!!raw &&
			(raw === 's' ||
				raw === 'secmeli' ||
				raw === 'elective' ||
				raw.includes('secmeli') ||
				raw.startsWith('elective'));

		if (imb === true) return true;
		if (imb === false) return typeMandatory;
		if (imb === 1 || imb === '1') return true;
		if (imb === 0 || imb === '0') return typeMandatory;
		if (typeMandatory) return true;
		if (typeElective) return false;
		return false;
	}

	/** Müfredat türü: tabloda Tür sütunu (zorunlu / seçmeli alt türü). */
	function curriculumKindColumnLabel(
		row:
			| Pick<DouEnrollment, 'type' | 'is_mandatory_course'>
			| Pick<AvailableCourse, 'type' | 'is_mandatory_course'>
	): string {
		if (douCourseIsMandatory(row)) return 'Zorunlu';
		const t = foldCourseTypeTr(String(row.type ?? ''));
		const electiveLabels: Record<string, string> = {
			teknik_secmeli: 'Teknik seçmeli',
			technical_elective: 'Teknik seçmeli',
			sosyal_secmeli: 'Sosyal seçmeli',
			social_elective: 'Sosyal seçmeli'
		};
		return electiveLabels[t] ?? 'Seçmeli';
	}

	/**
	 * Kart sırası (müfredat yarıyılı indeksi, çoğu 4×2) → «X. sınıf · Güz/Bahar».
	 */
	function obsCurriculumPlacementHint(raw: unknown): string | null {
		if (raw === null || raw === undefined || raw === '') return null;
		const k =
			typeof raw === 'number'
				? raw
				: typeof raw === 'string'
					? Number(raw.trim())
					: Number(raw);
		if (!Number.isFinite(k) || k < 1) return null;
		const ki = Math.floor(k);
		const sinif = Math.floor((ki - 1) / 2) + 1;
		const yariylInSinif = ((ki - 1) % 2) + 1;
		const halfTr = yariylInSinif === 1 ? 'Güz' : 'Bahar';
		return `${sinif}. sınıf · ${halfTr}`;
	}

	/** Açılan şubeler tablosu: sınıf + Güz/Bahar süzümü (ders kayıt & ekle-bırak). */
	let catalogSectionFilterKey = 'all';

	function catalogSlotKeyFromParts(classLabel: string, halfLabel: string): string {
		return `${classLabel.trim()}|${halfLabel.trim()}`;
	}

	function catalogSlotKeyFromCourse(c: AvailableCourse): string {
		const cl = String(c.catalog_class_label ?? '').trim();
		const hl = String(c.catalog_half_label ?? '').trim();
		if (!cl || cl === '—' || !hl || hl === '—') return '';
		return catalogSlotKeyFromParts(cl, hl);
	}

	function catalogSlotLabelFromKey(key: string): string {
		if (key === 'all') return 'Tümü — tüm sınıflar ve yarıyıllar';
		const idx = key.indexOf('|');
		if (idx < 0) return key;
		return `${key.slice(0, idx)} · ${key.slice(idx + 1)}`;
	}

	function catalogSectionsCountSummary(
		filtered: number,
		total: number,
		opts?: { realSections?: number; placeholders?: number }
	): string {
		const real = opts?.realSections;
		const ph = opts?.placeholders ?? 0;
		if (catalogFilterActive && total > 0) {
			let line = `${filtered} şube listeleniyor (toplam ${total})`;
			if (ph > 0 && real != null) {
				line = `${filtered} satır listeleniyor — ${real} şube (toplam ${total})`;
			}
			return line;
		}
		if (ph > 0 && real != null) {
			return `${total} satır · ${real} açık şube · ${ph} müfredat satırı`;
		}
		return `${total} açık şube`;
	}

	function defaultCatalogSlotKeyFromLimits(
		sections: AvailableCourse[],
		ps: number | null | undefined
	): string {
		const hint = obsCurriculumPlacementHint(ps);
		if (!hint) return 'all';
		const parts = hint.split(' · ');
		if (parts.length < 2) return 'all';
		const key = catalogSlotKeyFromParts(parts[0], parts[1]);
		if (!sections.some((c) => catalogSlotKeyFromCourse(c) === key)) return 'all';
		return key;
	}

	function syncCatalogSectionFilterDefault() {
		const ps =
			registrationLimits?.program_semester_number ?? profile?.program_semester_number;
		catalogSectionFilterKey = defaultCatalogSlotKeyFromLimits(availableCourses ?? [], ps);
	}

	$: catalogSlotFilterOptions = (() => {
		const seen = new Map<string, string>();
		for (const c of availableCourses ?? []) {
			const k = catalogSlotKeyFromCourse(c);
			if (k && !seen.has(k)) seen.set(k, catalogSlotLabelFromKey(k));
		}
		const slots = [...seen.entries()]
			.sort((a, b) => {
				const parse = (k: string) => {
					const [cl, hl] = k.split('|');
					const n = parseInt(cl, 10) || 0;
					return { n, hl: hl === 'Güz' ? 0 : 1 };
				};
				const pa = parse(a[0]);
				const pb = parse(b[0]);
				return pa.n !== pb.n ? pa.n - pb.n : pa.hl - pb.hl;
			})
			.map(([key, label]) => ({ key, label }));
		const ps =
			registrationLimits?.program_semester_number ?? profile?.program_semester_number;
		const defaultKey = defaultCatalogSlotKeyFromLimits(availableCourses ?? [], ps);
		if (defaultKey !== 'all') {
			const idx = slots.findIndex((s) => s.key === defaultKey);
			if (idx > 0) {
				const [first] = slots.splice(idx, 1);
				slots.unshift(first);
			}
		}
		return [...slots, { key: 'all', label: catalogSlotLabelFromKey('all') }];
	})();

	$: if (
		catalogSectionFilterKey &&
		catalogSectionFilterKey !== 'all' &&
		!catalogSlotFilterOptions.some((o) => o.key === catalogSectionFilterKey)
	) {
		catalogSectionFilterKey = defaultCatalogSlotKeyFromLimits(
			availableCourses ?? [],
			registrationLimits?.program_semester_number ?? profile?.program_semester_number
		);
	}

	$: filteredAvailableCourses =
		catalogSectionFilterKey === 'all'
			? (availableCourses ?? [])
			: (availableCourses ?? []).filter(
					(c) => catalogSlotKeyFromCourse(c) === catalogSectionFilterKey
				);

	$: catalogFilterActive = catalogSectionFilterKey !== 'all';

	function normMandatoryCourseCode(raw: string): string {
		return String(raw ?? '').trim().toUpperCase();
	}

	/**
	 * /registration-limits satırında ``curriculum_semester`` eksik gelirse, açılan şubede aynı ders kodu ile eşle.
	 */
	function resolvedMandatoryCurriculumSemester(
		m: Pick<CurriculumMandatoryBrief, 'course_code' | 'curriculum_semester'>,
		fromOffers: Map<string, number>
	): unknown {
		const ims = m.curriculum_semester as unknown;
		if (ims !== null && ims !== undefined && ims !== '') {
			const snum =
				typeof ims === 'number'
					? ims
					: typeof ims === 'string'
						? Number(ims.trim())
						: Number(ims);
			if (Number.isFinite(snum) && snum >= 1) return Math.floor(snum);
		}
		const codeKey = normMandatoryCourseCode(m.course_code ?? '');
		const hit = codeKey ? fromOffers.get(codeKey) : undefined;
		return hit ?? ims;
	}

	$: curriculumSemesterByOfferedCourseCode = (() => {
		const mp = new Map<string, number>();
		for (const c of availableCourses ?? []) {
			const key = normMandatoryCourseCode(c.course_code ?? '');
			const rawCs = (c as { curriculum_semester?: unknown }).curriculum_semester;
			if (!key || rawCs === null || rawCs === undefined || rawCs === '') continue;
			const n =
				typeof rawCs === 'number'
					? rawCs
					: typeof rawCs === 'string'
						? Number(rawCs.trim())
						: Number(rawCs);
			if (!Number.isFinite(n) || n < 1) continue;
			const vi = Math.floor(n);
			if (!mp.has(key)) mp.set(key, vi);
		}
		return mp;
	})();

	$: registrationPickRows = enrollments.filter((e) =>
		['active', 'pending', 'draft'].includes(e.status)
	);

	$: addDropTableRows = enrollments.filter(
		(x) =>
			['active', 'pending_drop', 'pending', 'draft'].includes(x.status) &&
			(x.status !== 'draft' || (x.enrollment_reason || '') === 'add_drop')
	);

	// --- NOT HESAPLAMA STATE ---
	let mockCourses: {
		code: string;
		name: string;
		akts: number;
		vize: number | null;
		vizeWeight: number;
		final: number | null;
		finalWeight: number;
		makeup: number | null;
		harf: string;
		gradePoint: number;
	}[] = [];

	function calculateHarf(score: number): { harf: string; point: number } {
		if (score >= 95) return { harf: 'A+', point: 4.0 };
		if (score >= 90) return { harf: 'A', point: 3.75 };
		if (score >= 85) return { harf: 'B+', point: 3.5 };
		if (score >= 75) return { harf: 'B', point: 3.0 };
		if (score >= 65) return { harf: 'C+', point: 2.5 };
		if (score >= 55) return { harf: 'C', point: 2.0 };
		if (score >= 45) return { harf: 'D+', point: 1.5 };
		if (score >= 40) return { harf: 'D', point: 1.0 };
		return { harf: 'F', point: 0.0 };
	}

	function updateMockCalculations() {
		mockCourses = mockCourses.map((c) => {
			const v = c.vize ?? 0;
			const f = c.final ?? 0;
			const m = c.makeup;
			
			// Eğer büt girilmişse final yerine büt kullanılır (ağırlığı aynı)
			const effectiveFinal = (m !== null && m !== undefined) ? m : f;
			const total = (v * c.vizeWeight) / 100 + (effectiveFinal * c.finalWeight) / 100;
			
			const res = calculateHarf(total);
			return { ...c, harf: res.harf, gradePoint: res.point };
		});
	}

	type MockCourseRow = (typeof mockCourses)[number];

	/** Vize/final ağırlıklarıyla 100 üzerinden ders notu ve katkı parçaları */
	function getMockCourseBreakdown(c: MockCourseRow): {
		vNum: number;
		fEff: number;
		vizePart: number;
		finalPart: number;
		total: number;
		usesMakeup: boolean;
	} {
		const vNum = Number(c.vize ?? 0);
		const m = c.makeup;
		const usesMakeup = m !== null && m !== undefined;
		const fEff = Number((usesMakeup ? m : c.final) ?? 0);
		const vizePart = (vNum * c.vizeWeight) / 100;
		const finalPart = (fEff * c.finalWeight) / 100;
		return {
			vNum,
			fEff,
			vizePart,
			finalPart,
			total: vizePart + finalPart,
			usesMakeup
		};
	}

	/** Şubede ağırlık yok / eski kayıtta API varsayılanı (40/60). */
	const LISTED_GRADE_VIZE_PCT = 40;
	const LISTED_GRADE_FINAL_PCT = 60;

	function listedGradeWeighted100(g: DouGradeEntry): {
		vNum: number;
		fNum: number;
		vPart: number;
		fPart: number;
		total: number;
		usesMakeup: boolean;
		vw: number;
		wf: number;
	} | null {
		if (g.midterm === null || g.midterm === undefined) return null;
		const usesMakeup = g.makeup !== null && g.makeup !== undefined;
		const fSrc = usesMakeup ? g.makeup : g.final;
		if (fSrc === null || fSrc === undefined) return null;
		const vNum = Number(g.midterm);
		const fNum = Number(fSrc);
		if (Number.isNaN(vNum) || Number.isNaN(fNum)) return null;
		const vwRaw = g.midterm_weight_percent;
		const wfRaw = g.final_weight_percent;
		const vw =
			typeof vwRaw === 'number' && Number.isFinite(vwRaw) && vwRaw >= 0
				? vwRaw
				: LISTED_GRADE_VIZE_PCT;
		const wf =
			typeof wfRaw === 'number' && Number.isFinite(wfRaw) && wfRaw >= 0
				? wfRaw
				: LISTED_GRADE_FINAL_PCT;
		const vPart = (vNum * vw) / 100;
		const fPart = (fNum * wf) / 100;
		return {
			vNum,
			fNum,
			vPart,
			fPart,
			total: vPart + fPart,
			usesMakeup,
			vw,
			wf
		};
	}

	$: mockAno = (() => {
		if (mockCourses.length === 0) return 0;
		const totalPoints = mockCourses.reduce((acc, c) => acc + c.gradePoint * c.akts, 0);
		const totalAkts = mockCourses.reduce((acc, c) => acc + c.akts, 0);
		return totalAkts > 0 ? totalPoints / totalAkts : 0;
	})();

	$: projectedAgno = (() => {
		const currentGpa = cumulativeGpa ?? 0;
		const currentAkts = transcriptTotalAkts ?? 0;
		const newAkts = mockCourses.reduce((acc, c) => acc + c.akts, 0);
		const newPoints = mockCourses.reduce((acc, c) => acc + c.gradePoint * c.akts, 0);

		if (currentAkts + newAkts === 0) return currentGpa;
		return (currentGpa * currentAkts + newPoints) / (currentAkts + newAkts);
	})();

	function initMockFromEnrollments() {
		if (enrollments.length > 0) {
			mockCourses = enrollments
				.filter((e) => e.status === 'active')
				.map((e) => ({
					code: e.course_code,
					name: e.course_name,
					akts: e.akts,
					vize: null,
					vizeWeight: 40,
					final: null,
					finalWeight: 60,
					makeup: null,
					harf: 'F',
					gradePoint: 0
				}));
		}
	}

	function addMockCourse() {
		mockCourses = [
			...mockCourses,
			{
				code: 'YENI',
				name: 'Yeni Ders',
				akts: 5,
				vize: null,
				vizeWeight: 40,
				final: null,
				finalWeight: 60,
				makeup: null,
				harf: 'F',
				gradePoint: 0
			}
		];
	}

	function removeMockCourse(index: number) {
		mockCourses = mockCourses.filter((_, i) => i !== index);
	}

	let curriculum: {
		program?: string;
		overall_progress_pct?: number;
		categories?: {
			name: string;
			courses: {
				code: string;
				name: string;
				akts: number;
				status: string;
				grade?: string | null;
			}[];
		}[];
	} | null = null;
	/** Ders kayıt başlığı — API’deki aktif dönem adı */
	let enrollmentTermLabel = '—';

	/** Kayıt kuralları (GNO / hazırlık) — GET /student/me/registration-limits */
	let registrationLimits: DouStudentRegistrationLimits | null = null;
	$: aktsMax = registrationLimits?.akts_max ?? 30;
	$: aktsLimitHint = (() => {
		const r = registrationLimits;
		if (!r) return '';
		const gno =
			r.gpa_computed != null
				? `${r.gpa_computed.toFixed(2)} (ΣAKTS payda: ${r.akts_counted_in_gpa ?? 0})`
				: (r.gpa?.toFixed(2) ?? '—');
		const profNote =
			r.gpa_profile != null &&
			r.gpa_computed != null &&
			Math.abs(r.gpa_profile - r.gpa_computed) > 0.005
				? ` Profilde kayıtlı GNO: ${r.gpa_profile.toFixed(2)}.`
				: '';
		if (r.rule === 'prep') return `Hazırlık: en fazla ${r.akts_max} AKTS.`;
		if (r.rule === 'early_semesters')
			return `1.–2. program yarıyılı (kayıtlı: ${r.program_semester_number ?? 1}): Madde 23 gereği ek AKTS yok; üst sınır ${r.akts_max} AKTS.${profNote}`;
		if (r.rule === 'low_gpa')
			return `GNO ${gno} < ${r.min_gpa_for_high_akts}: üst sınır ${r.akts_max} AKTS.${profNote}`;
		if (r.rule === 'mid_gpa')
			return `${r.min_gpa_for_high_akts} ≤ GNO (${gno}) < ${r.min_gpa_for_top_akts}: üst sınır ${r.akts_max} AKTS.${profNote}`;
		if (r.rule === 'top_gpa')
			return `GNO ${gno} ≥ ${r.min_gpa_for_top_akts}: üst sınır ${r.akts_max} AKTS.${profNote}`;
		if (r.rule === 'high_gpa')
			return `Yüksek GNO: üst sınır ${r.akts_max} AKTS.${profNote}`;
		return `Üst sınır ${r.akts_max} AKTS (yıldız: ${r.akts_limit_default} / ${r.akts_limit_high} / ${r.akts_limit_top}). GNO: ${gno}.${profNote}`;
	})();

	// Profil düzenleme
	let profileEdit = false;
	let profileForm = {
		full_name: '',
		phone: '',
		address: '',
		emergency_contact: '',
		emergency_phone: ''
	};
	let profileSaving = false;
	let profileSaved = false;
	let profileError: string | null = null;

	// Ders Kayıt — taslaklar (status=draft)
	let enrollSubmitting = false;
	let enrollSuccess: string | null = null;
	let enrollError: string | null = null;

	/** Ders ekle-bırak — bırakılacak satır id kümesi (danışmana göndermeden önce) */
	let markedDrop: Set<string> = new Set();
	let dropSubmitting = false;
	let dropSuccess: string | null = null;
	let dropError: string | null = null;
	let addDropTermLabel = '—';

	$: draftEnrollments = enrollments.filter(
		(e) => e.status === 'draft' && (e.enrollment_reason || '') !== 'add_drop'
	);
	$: hasPendingRegistration = enrollments.some((e) => e.status === 'pending');
	$: draftAkts = draftEnrollments.reduce((s, e) => s + e.akts, 0);
	/** Dönem yükü (API ile aynı: active + pending + draft + pending_drop) */
	$: enrollmentScheduledAkts = enrollments
		.filter((e) => ['active', 'pending', 'draft', 'pending_drop'].includes(e.status))
		.reduce((s, e) => s + (e.akts || 0), 0);
	$: addDropDraftRows = enrollments.filter(
		(e) => e.status === 'draft' && (e.enrollment_reason || '') === 'add_drop'
	);
	$: hasPendingAddDrop = enrollments.some(
		(e) => e.status === 'pending' || e.status === 'pending_drop'
	);

	$: addDropAktsMin = registrationLimits?.add_drop_akts_min ?? 30;
	$: addDropAktsMax = registrationLimits?.add_drop_akts_max ?? 30;
	/** Planlanan yük: kayıtlı aktif satırlar her zaman dahil; yalnızca kartı uyuşmayan *taslak (eklenecek)* satırlar düşülür (backend ile aynı). */
	$: addDropProjectedAkts = enrollments.reduce((s, e) => {
		if (e.status === 'active' && !markedDrop.has(e.id)) return s + (e.akts || 0);
		if (e.status === 'draft' && (e.enrollment_reason || '') === 'add_drop') {
			if ((e.add_drop_curriculum_slot_match ?? true) !== true) return s;
			return s + (e.akts || 0);
		}
		return s;
	}, 0);
	$: addDropAktsBoundsOk =
		addDropProjectedAkts >= addDropAktsMin && addDropProjectedAkts <= addDropAktsMax;
	$: addDropAktsOk = addDropAktsBoundsOk;
	$: addDropAktsRuleHint = (() => {
		const g =
			registrationLimits?.gpa_computed ??
			registrationLimits?.gpa ??
			registrationLimits?.gpa_profile;
		const gtxt = g != null ? g.toFixed(2) : '—';
		return `Ders ekle-bırak: planlanan dönem yükü ${addDropProjectedAkts} AKTS (zorunlu aralık ${addDropAktsMin}–${addDropAktsMax} AKTS). GNO: ${gtxt}.`;
	})();

	// Kayıt Penceresi Kontrolü
	$: activeTerm = terms.find((t) => t.is_active) ?? terms[terms.length - 1];
	$: isWindowOpen = (() => {
		if (!activeTerm) return true; // Henüz yüklenmediyse gösterme
		if (apiKey === 'ders-kayit') return activeTerm.registration_open !== false;
		if (apiKey === 'ders-ekle') return activeTerm.add_drop_open === true;
		return true;
	})();

	// Belge talebi
	let docForm = {
		requesting_institution: '',
		request_reason: '',
		document_type: 'öğrenci_belgesi',
		document_subtype: 'Türkçe'
	};
	let docSubmitting = false;
	let docSuccess: string | null = null;
	let docError: string | null = null;
	const DOC_SUBTYPES: Record<string, string[]> = {
		transkript: ['Resmi', 'Onaysız'],
		öğrenci_belgesi: ['Türkçe', 'İngilizce'],
		disiplin_belgesi: ['Türkçe', 'İngilizce']
	};
	$: docSubtypes = DOC_SUBTYPES[docForm.document_type] ?? ['Türkçe'];

	// Mesaj yaz
	let showCompose = false;
	let composeForm = {
		subject: '',
		body: '',
		receiver_name: 'Danışmanım',
		receiver_type: 'akademisyen'
	};
	let composeSending = false;
	let composeSuccess: string | null = null;
	let composeError: string | null = null;

	// Şifre değiştir
	let pwForm = { current_password: '', new_password: '', confirm_password: '' };
	let pwErr: string | null = null;
	let pwOk: string | null = null;
	let pwBusy = false;

	function normTermKey(id: unknown): string {
		return String(id ?? '')
			.trim()
			.toLowerCase()
			.replace(/[{}]/g, '');
	}

	/**
	 * Ders Kayıt / Ekle-Bırak: OBS’te işaretli akademik süre; liste ve AKTS bununla süzülür.
	 * (Takvim aktif süre yoksa API ile uyum için son sıradaki döneme düşülür.)
	 */
	function resolvedRegistrationTermIdFromList(tl: DouTerm[]): string {
		const list = tl ?? [];
		if (!list.length) return '';
		const hit = list.find((t) => t.is_active);
		if (hit?.id != null && String(hit.id).trim() !== '')
			return String(hit.id).trim();
		const tail = list[list.length - 1];
		return tail?.id != null ? String(tail.id).trim() : '';
	}

	$: gradesGrouped = ((): { key: string; label: string; rows: DouGradeEntry[] }[] => {
		if (!grades?.length) return [];
		const by = new Map<string, DouGradeEntry[]>();
		for (const g of grades) {
			const id = normTermKey(g.term_id);
			if (!by.has(id)) by.set(id, []);
			by.get(id)!.push(g);
		}
		const termOrder = [...terms].sort(
			(a, b) =>
				new Date(b.starts_at || 0).getTime() - new Date(a.starts_at || 0).getTime()
		);
		const out: { key: string; label: string; rows: DouGradeEntry[] }[] = [];
		const seen = new Set<string>();
		for (const t of termOrder) {
			const bid = normTermKey(t.id);
			const rs = by.get(bid);
			if (!rs?.length) continue;
			out.push({
				key: String(t.id),
				label: (t.name ?? '').trim() || (rs[0]?.term_name ?? '').trim() || bid.slice(0, 8),
				rows: rs
			});
			seen.add(bid);
		}
		for (const [bid, grpRows] of by.entries()) {
			if (seen.has(bid) || !grpRows.length) continue;
			out.push({
				key: bid,
				label: (grpRows[0]?.term_name ?? '').trim() || bid.slice(0, 8),
				rows: grpRows
			});
		}
		return out;
	})();

	/** Notlar sekmesi: varsayılan dönemi, öğrencinin gerçek kayıtlarındaki en güncel `term_id` ile hizala. */
	function pickGradeDefaultTermFromEnrollments(
		enr: DouEnrollment[],
		tl: DouTerm[]
	): string {
		const ids = new Set((tl ?? []).map((t) => t.id));
		const termStart = new Map<string, number>(
			(tl ?? []).map((t) => [t.id, new Date(t.starts_at || 0).getTime()])
		);
		let bestTid = '';
		let bestTs = Number.NEGATIVE_INFINITY;
		for (const e of enr ?? []) {
			const tid = e.term_id;
			if (!tid || !ids.has(tid)) continue;
			const ts = termStart.get(tid);
			const n = typeof ts === 'number' && !Number.isNaN(ts) ? ts : 0;
			if (n >= bestTs) {
				bestTs = n;
				bestTid = tid;
			}
		}
		return bestTid;
	}

	async function reloadAttendanceForTerm(termIdExplicit?: string) {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;
		loading = true;
		loadErr = null;
		try {
			const tidRaw = termIdExplicit ?? selectedAttendanceTermId;
			const r = await getDouStudentAttendance(token, tidRaw || undefined);
			attendance = r?.attendance ?? [];
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Devamsızlık yüklenemedi.';
		} finally {
			loading = false;
		}
	}

	async function reloadGradesForTerm(termIdExplicit?: string) {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;
		loading = true;
		loadErr = null;
		try {
			const raw = String(termIdExplicit ?? selectedGradesTermId ?? '').trim();
			const tid = raw || undefined;
			const termLabel =
				tid && terms?.length ? terms.find((t) => t.id === tid)?.name ?? tid : '(tümü / parametresiz)';
			console.log('[OBS Not Listesi] Dönem değişti — yükleme', {
				selectedTermId: tid ?? '(yok)',
				termLabel,
				apiPath: `/student/me/grades${tid ? `?term_id=${encodeURIComponent(tid)}` : ''}`
			});
			const r = await getDouStudentGrades(token, tid);
			grades = r?.grades ?? [];
			console.log('[OBS Not Listesi] Yanıt', {
				gradeCount: grades.length,
				rowsPreview: grades.slice(0, 8).map((g) => ({
					code: g.course_code,
					term_id: g.term_id,
					vize: g.midterm,
					final: g.final,
					harf: g.letter_grade
				}))
			});
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Notlar yüklenemedi.';
			console.warn('[OBS Not Listesi] Hata', loadErr);
		} finally {
			loading = false;
		}
	}

	async function reloadScheduleForTerm(termIdExplicit?: string) {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;
		loading = true;
		loadErr = null;
		try {
			const raw = String(termIdExplicit ?? selectedScheduleTermId ?? '').trim();
			const tid = raw || undefined;
			const r = await getDouStudentSchedule(token, tid);
			schedule = r?.schedule ?? [];
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Ders programı yüklenemedi.';
		} finally {
			loading = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Veri yükleme
	// ---------------------------------------------------------------------------
	async function loadPage() {
		if (!browser || !apiKey) return;
		loading = true;
		loadErr = null;
		const token = localStorage.token ?? null;
		if (!token) {
			loadErr = 'Giriş yapmanız gerekiyor.';
			loading = false;
			return;
		}

		try {
			addDropSectionsEmptyHint = '';
			addDropSectionsInTermTotal = null;
			addDropSectionsQueryRowsStudent = null;
			addDropCoursesPendingSections = [];
			addDropRealSectionRowCount = 0;
			addDropOfferPlaceholderRowsMeta = 0;
			registrationSectionsEmptyHint = '';
			registrationSectionsInTermTotal = null;
			registrationSectionsQueryRowsStudent = null;
			registrationRealSectionRowCount = 0;
			registrationOfferPlaceholderRowsMeta = 0;

			if (apiKey === 'profile') {
				profile = await getDouStudentProfile(token).catch(() => null);
				if (profile) {
					const p = profile as unknown as Record<string, string>;
					profileForm = {
						full_name: profile.full_name ?? profile.email ?? '',
						phone: p['phone'] ?? '',
						address: p['address'] ?? '',
						emergency_contact: p['emergency_contact'] ?? '',
						emergency_phone: p['emergency_phone'] ?? ''
					};
				} else {
					profileForm = {
						full_name: '',
						phone: '',
						address: '',
						emergency_contact: '',
						emergency_phone: ''
					};
				}
			}
			if (apiKey === 'calendar') {
				await reloadCalendarDocs();
			}
			if (apiKey === 'terms') terms = await getDouTerms(token).catch(() => []);
			if (apiKey === 'advisor') advisor = await getDouStudentAdvisor(token).catch(() => null);
			if (apiKey === 'enrollments') {
				const r = await getDouStudentEnrollments(token).catch(() => null);
				enrollments = r?.enrollments ?? [];
				totalAkts = r?.total_akts ?? 0;
			}
			if (apiKey === 'ders-ekle') {
				const tl = await getDouTerms(token).catch(() => [] as DouTerm[]);
				terms = tl;
				const regTid = resolvedRegistrationTermIdFromList(tl);
				const [enrRes, avRes] = await Promise.allSettled([
					getDouStudentEnrollments(token, regTid || undefined, 'active,draft,pending,pending_drop'),
					getDouAvailableCourses(token, regTid || undefined, { forAddDrop: true })
				]);
				if (enrRes.status === 'fulfilled') {
					enrollments = enrRes.value.enrollments;
					totalAkts = enrRes.value.total_akts ?? 0;
				} else {
					enrollments = [];
					totalAkts = 0;
				}
				if (avRes.status === 'fulfilled') {
					const av = avRes.value as DouAvailableCoursesResponse;
					availableCourses = av.sections ?? [];
					addDropSectionsEmptyHint = av.add_drop_sections_empty_hint ?? '';
					addDropSectionsInTermTotal =
						typeof av.sections_in_terms_total === 'number' ? av.sections_in_terms_total : null;
					addDropSectionsQueryRowsStudent =
						typeof av.sections_query_rows_student === 'number'
							? av.sections_query_rows_student
							: null;
					addDropCoursesPendingSections = Array.isArray(av.courses_pending_sections)
						? av.courses_pending_sections
						: [];
					addDropRealSectionRowCount =
						typeof av.real_section_rows_emitted === 'number'
							? av.real_section_rows_emitted
							: 0;
					addDropOfferPlaceholderRowsMeta =
						typeof av.offer_placeholder_rows === 'number'
							? av.offer_placeholder_rows
							: 0;
				} else {
					availableCourses = [];
				}
				const at = tl.find((t) => t.is_active) ?? tl[tl.length - 1];
				addDropTermLabel = at?.name ?? '—';
				registrationLimits = await getDouStudentRegistrationLimits(
					token,
					regTid || undefined
				).catch(() => null);
				syncCatalogSectionFilterDefault();
				if (browser && import.meta.env.DEV) {
					const avPayload =
						avRes.status === 'fulfilled'
							? (avRes.value as DouAvailableCoursesResponse)
							: null;
					const sec = availableCourses ?? [];
					console.groupCollapsed(
						'[OBS Dev] Ders ekle/bırak — dönem + müfredat + açılan şubeler kaynağı'
					);
					console.log('Takvim / istek:', {
						regTidResolved: regTid || '(yok)',
						for_add_drop_api: true,
						uiDonemEtiketi: addDropTermLabel
					});
					console.log('/student/available-courses yanıtı term_id:', avPayload?.term_id ?? '(yok)');
					console.log('Meta (liste filtresi):', {
						program_semester_number:
							avPayload?.program_semester_number ??
							registrationLimits?.program_semester_number,
						department_id: avPayload?.department_id ?? registrationLimits?.department_id,
						curriculum_filter_active: avPayload?.curriculum_filter_active
					});
					console.log(
						'registration-limits müfredat eksikleri (zorunlu kapısı):',
						(registrationLimits?.curriculum_mandatory_remaining ?? []).map((m) => {
							const rcs = resolvedMandatoryCurriculumSemester(
								m,
								curriculumSemesterByOfferedCourseCode
							);
							const pl = obsCurriculumPlacementHint(rcs);
							return `${m.course_code ?? '?'} (${m.akts ?? '?'} AKTS)${pl ? ` — ${pl}` : ''}`;
						})
					);
					if (avRes.status === 'rejected') {
						console.warn('[OBS Dev] available-courses yükleme hatası:', avRes.reason);
					}
					console.log(
						`Açılan şube satırı: ${sec.length} (SQL: seçilen akademik süre eşlemesi)`
					);
					console.log('[OBS Dev] Şube/teşhis', {
						sections_in_terms_total: avPayload?.sections_in_terms_total,
						sections_query_rows_student: avPayload?.sections_query_rows_student,
						real_sections: avPayload?.real_section_rows_emitted,
						offer_placeholders: avPayload?.offer_placeholder_rows,
						pending_mandatory_codes: (avPayload?.courses_pending_sections ?? []).length,
						add_drop_sections_empty_hint: avPayload?.add_drop_sections_empty_hint
					});
					console.table(
						sec.map((c) => ({
							kod: c.course_code,
							raw_type: (c.type ?? '') as string,
							is_mandatory_course_api: Boolean(c.is_mandatory_course),
							curriculum_semester_kart: c.curriculum_semester ?? '—',
							sec_id_kisa: ((c.id as string) || '').slice(0, 8)
						}))
					);
					console.info(
						'Tür/Zorunlu etiketi: API tarafından sağlanır. Yanlışsa veri kaynağı güncellenmelidir; UI sadece API’yi yansıtır.'
					);
					console.groupEnd();
				}
			}
			if (apiKey === 'ders-kayit') {
				const tl = await getDouTerms(token).catch(() => [] as DouTerm[]);
				terms = tl;
				const regTid = resolvedRegistrationTermIdFromList(tl);
				const [enrRes, avRes] = await Promise.allSettled([
					getDouStudentEnrollments(token, regTid || undefined, 'draft,pending,active'),
					getDouAvailableCourses(token, regTid || undefined)
				]);
				if (enrRes.status === 'fulfilled') {
					enrollments = enrRes.value.enrollments;
					totalAkts = enrRes.value.total_akts ?? 0;
				} else {
					enrollments = [];
					totalAkts = 0;
				}
				if (avRes.status === 'fulfilled') {
					const av = avRes.value as DouAvailableCoursesResponse;
					availableCourses = av.sections ?? [];
					registrationSectionsEmptyHint = av.registration_sections_empty_hint ?? '';
					registrationSectionsInTermTotal =
						typeof av.sections_in_terms_total === 'number' ? av.sections_in_terms_total : null;
					registrationSectionsQueryRowsStudent =
						typeof av.sections_query_rows_student === 'number'
							? av.sections_query_rows_student
							: null;
					registrationRealSectionRowCount =
						typeof av.real_section_rows_emitted === 'number' ? av.real_section_rows_emitted : 0;
					registrationOfferPlaceholderRowsMeta =
						typeof av.offer_placeholder_rows === 'number' ? av.offer_placeholder_rows : 0;
				} else {
					availableCourses = [];
				}
				const at = tl.find((t) => t.is_active) ?? tl[tl.length - 1];
				enrollmentTermLabel = at?.name ?? '—';
				registrationLimits = await getDouStudentRegistrationLimits(
					token,
					regTid || undefined
				).catch(() => null);
				syncCatalogSectionFilterDefault();
			}
			if (apiKey === 'grades') {
				const [trRes, enrRes] = await Promise.all([
					getDouTerms(token),
					getDouStudentEnrollments(
						token,
						undefined,
						'active,pending,pending_drop,draft'
					).catch(() => null)
				]);
				terms = trRes ?? [];
				const enrollList = enrRes?.enrollments ?? [];
				if (terms.length) {
					const calendarActiveId = terms.find((t) => t.is_active)?.id ?? '';
					const tailId = terms[terms.length - 1]?.id ?? '';
					const defLegacy = calendarActiveId || tailId;
					const fromEnr = pickGradeDefaultTermFromEnrollments(enrollList, terms);
					const activeHasEnrollment =
						!!calendarActiveId &&
						enrollList.some((e) => e.term_id === calendarActiveId);
					const def = activeHasEnrollment
						? calendarActiveId
						: fromEnr || defLegacy;
					if (
						!selectedGradesTermId ||
						!terms.some((x) => x.id === selectedGradesTermId)
					) {
						selectedGradesTermId = def;
					}
				} else {
					selectedGradesTermId = '';
				}
				const tid = selectedGradesTermId ? selectedGradesTermId : undefined;
				const gr = await getDouStudentGrades(token, tid).catch(() => null);
				grades = gr?.grades ?? [];
			}
			if (apiKey === 'gpa') {
				const r = await getDouStudentGpaSummary(token).catch(() => null);
				gpaTerms = r?.terms ?? [];
				cumulativeGpa = r?.cumulative_gpa ?? null;
			}
			if (apiKey === 'transcript') {
				const r = await getDouStudentTranscript(token).catch(() => null);
				transcript = r?.transcript ?? [];
				cumulativeGpa = r?.cumulative_gpa ?? null;
				transcriptTotalAkts = (r as { total_akts?: number } | null)?.total_akts ?? null;
			}
			if (apiKey === 'attendance') {
				const tr = await getDouTerms(token).catch(() => []);
				terms = tr;
				const def = terms.find((t) => t.is_active)?.id ?? terms[terms.length - 1]?.id ?? '';
				if (
					!selectedAttendanceTermId ||
					!terms.some((x) => x.id === selectedAttendanceTermId)
				) {
					selectedAttendanceTermId = def;
				}
				const r = await getDouStudentAttendance(
					token,
					selectedAttendanceTermId || undefined
				).catch(() => null);
				attendance = r?.attendance ?? [];
			}
			if (apiKey === 'exams') {
				const r = await getDouStudentExams(token).catch(() => null);
				exams = r?.exams ?? [];
			}
			if (apiKey === 'schedule') {
				const tr = await getDouTerms(token).catch(() => []);
				terms = tr ?? [];
				if (terms.length) {
					const def =
						terms.find((t) => t.is_active)?.id ?? terms[terms.length - 1]?.id ?? '';
					if (
						!selectedScheduleTermId ||
						!terms.some((x) => x.id === selectedScheduleTermId)
					) {
						selectedScheduleTermId = def;
					}
				} else {
					selectedScheduleTermId = '';
				}
				const tid = selectedScheduleTermId ? selectedScheduleTermId : undefined;
				const r = await getDouStudentSchedule(token, tid).catch(() => null);
				schedule = r?.schedule ?? [];
			}
			if (apiKey === 'announcements') {
				const r = await getDouStudentAnnouncements(token).catch(() => null);
				announcements = r?.announcements ?? [];
			}
			if (apiKey === 'inbox') {
				const r = await getDouInbox(token).catch(() => null);
				inboxMsgs = r?.messages ?? [];
			}
			if (apiKey === 'sent') {
				const r = await getDouSent(token).catch(() => null);
				sentMsgs = r?.messages ?? [];
			}
			if (apiKey === 'doc-request') {
				const r = await getDouStudentDocumentRequests(token).catch(() => null);
				docRequests = r?.requests ?? [];
			}
			if (apiKey === 'curriculum') {
				const r = await getDouCurriculumStatus(token).catch(() => null);
				curriculum = (r as typeof curriculum) ?? null;
			}
			if (apiKey === 'not-hesaplama') {
				const [enrRes, gpaRes, transRes] = await Promise.allSettled([
					getDouStudentEnrollments(token, undefined, 'active'),
					getDouStudentRegistrationLimits(token),
					getDouStudentTranscript(token)
				]);
				if (enrRes.status === 'fulfilled') {
					enrollments = enrRes.value.enrollments;
					initMockFromEnrollments();
				}
				if (gpaRes.status === 'fulfilled') {
					registrationLimits = gpaRes.value;
					cumulativeGpa = gpaRes.value.gpa_computed ?? gpaRes.value.gpa ?? gpaRes.value.gpa_profile ?? 0;
				}
				if (transRes.status === 'fulfilled') {
					transcriptTotalAkts = (transRes.value as { total_akts?: number })?.total_akts ?? 0;
				}
			}
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'API hatası.';
		} finally {
			loading = false;
		}
	}

	/** Danışmanın WebUI kullanıcı kimliği — POST /messages için zorunlu. */
	async function resolveAdvisorReceiverUserId(token: string): Promise<string | null> {
		if (advisor?.advisor?.academic_user_id) return advisor.advisor.academic_user_id;
		const r = await getDouStudentAdvisor(token).catch(() => null);
		advisor = r;
		return r?.advisor?.academic_user_id ?? null;
	}

	// Svelte 5: $: loadPage(...) + apiKey bağımlılığı döngü / kilitlenmeye yol açabiliyor; sadece navigasyon sonrası yükle.
	afterNavigate(async () => {
		await tick();
		if (!browser) return;
		void loadPage();
	});

	// ---------------------------------------------------------------------------
	// Aksiyonlar
	// ---------------------------------------------------------------------------
	async function saveProfile() {
		profileSaving = true;
		profileSaved = false;
		profileError = null;
		const token = localStorage.token ?? null;
		try {
			await updateDouStudentProfile(token, {
				full_name: profileForm.full_name || undefined,
				phone: profileForm.phone || undefined,
				address: profileForm.address || undefined,
				emergency_contact: profileForm.emergency_contact || undefined,
				emergency_phone: profileForm.emergency_phone || undefined
			});
			profileSaved = true;
			profileEdit = false;
			await loadPage();
		} catch (e: unknown) {
			profileError = e instanceof Error ? e.message : 'Kaydetme hatası.';
		} finally {
			profileSaving = false;
		}
	}

	function toggleCart(course: AvailableCourse) {
		// Senkron imza korunur; async işlem aşağıda
		void toggleCartAsync(course);
	}

	async function toggleCartAsync(course: AvailableCourse) {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;
		const existing = enrollments.find(
			(e) =>
				e.status === 'draft' &&
				e.section_id === course.id &&
				(e.enrollment_reason || '') !== 'add_drop'
		);
		enrollError = null;
		if (hasPendingRegistration) {
			enrollError = 'Listeniz danışman onayında; değişiklik yapılamaz.';
			setTimeout(() => (enrollError = null), 4000);
			return;
		}
		if (
			(course as AvailableCourse & { offer_placeholder?: boolean }).offer_placeholder === true ||
			!String(course.id || '').trim()
		) {
			enrollError =
				'Bu satır için şube tanımı gerekir — şubesiz seçim yapılamaz.';
			setTimeout(() => (enrollError = null), 5000);
			return;
		}
		try {
			if (existing) {
				await deleteDouDraftEnrollment(token, existing.id);
			} else {
				const maxAkts = registrationLimits?.akts_max ?? 30;
				if (enrollmentScheduledAkts + course.akts > maxAkts) {
					enrollError = `AKTS limitini aşıyor (maks. ${maxAkts}, mevcut: ${enrollmentScheduledAkts}).`;
					setTimeout(() => (enrollError = null), 4000);
					return;
				}
				await postDouDraftEnrollments(token, [course.id], 'registration');
			}
			await loadPage();
		} catch (e: unknown) {
			enrollError = e instanceof Error ? e.message : 'İşlem yapılamadı.';
		}
	}

	async function removeDraftEnrollmentRow(enrollmentId: string) {
		const token = localStorage.token ?? null;
		if (!token) return;
		enrollError = null;
		dropError = null;
		try {
			await deleteDouDraftEnrollment(token, enrollmentId);
			await loadPage();
		} catch (e: unknown) {
			const msg = e instanceof Error ? e.message : 'Silinemedi.';
			if (apiKey === 'ders-ekle') dropError = msg;
			else enrollError = msg;
		}
	}

	async function clearAllDraftEnrollments() {
		const token = localStorage.token ?? null;
		if (!token) return;
		enrollError = null;
		try {
			await Promise.all(draftEnrollments.map((e) => deleteDouDraftEnrollment(token, e.id)));
			await loadPage();
		} catch (e: unknown) {
			enrollError = e instanceof Error ? e.message : 'Temizlenemedi.';
		}
	}

	async function finalizeEnrollment() {
		if (!draftEnrollments.length) return;
		
		const minAkts = registrationLimits?.akts_min ?? 30;
		if (enrollmentScheduledAkts < minAkts) {
			enrollError = `Danışman onayına göndermek için en az ${minAkts} AKTS seçmelisiniz (Mevcut: ${enrollmentScheduledAkts}).`;
			setTimeout(() => (enrollError = null), 5000);
			return;
		}

		enrollSubmitting = true;
		enrollSuccess = null;
		enrollError = null;
		const token = localStorage.token ?? null;
		try {
			await submitDouStudentSchedule(token, undefined);
			const dersListesi = draftEnrollments
				.map((e) => `• ${e.course_code} — ${e.course_name} (${e.akts} AKTS)`)
				.join('\n');
			const advisorRid = await resolveAdvisorReceiverUserId(token);
			if (advisorRid) {
				await sendDouMessageApi(token, {
					receiver_user_id: advisorRid,
					receiver_name: 'Danışmanım',
					receiver_type: 'akademisyen',
					subject: 'Ders Kayıt — Danışman onayı',
					body: `Sayın Danışmanım,\n\nDers kayıt listemi onayınıza gönderdim:\n\n${dersListesi}\n\nToplamda ${draftAkts} AKTS. Saygılarımla`
				}).catch(() => {
					/* mesaj isteğe bağlı */
				});
			}
			const courseNames = draftEnrollments.map((e) => e.course_code).join(', ');
			enrollSuccess = `${draftEnrollments.length} ders (${courseNames}) danışman onayına gönderildi; liste kilitlendi.`;
			await loadPage();
		} catch (e: unknown) {
			enrollError = e instanceof Error ? e.message : 'İstek gönderilemedi.';
		} finally {
			enrollSubmitting = false;
		}
	}

	function toggleDrop(enrollmentId: string) {
		if (hasPendingAddDrop) return;
		const s = new Set(markedDrop);
		if (s.has(enrollmentId)) s.delete(enrollmentId);
		else s.add(enrollmentId);
		markedDrop = s;
	}

	async function toggleAddDropCartAsync(course: AvailableCourse) {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token) return;
		const existing = enrollments.find(
			(e) =>
				e.status === 'draft' &&
				e.section_id === course.id &&
				(e.enrollment_reason || '') === 'add_drop'
		);
		dropError = null;
		if (hasPendingAddDrop) {
			dropError = 'Listeniz danışman onayında; değişiklik yapılamaz.';
			setTimeout(() => (dropError = null), 4000);
			return;
		}
		if (
			(course as AvailableCourse & { offer_placeholder?: boolean }).offer_placeholder === true ||
			!String(course.id || '').trim()
		) {
			dropError =
				'Bu satır için şube tanımı gerekir — şubesiz seçim yapılamaz.';
			setTimeout(() => (dropError = null), 5000);
			return;
		}
		try {
			if (existing) {
				await deleteDouDraftEnrollment(token, existing.id);
			} else {
				const maxAd = registrationLimits?.add_drop_akts_max ?? 30;
				if (addDropProjectedAkts + course.akts > maxAd) {
					dropError = `AKTS üst sınırı (${maxAd}) aşılır (planlanan: ${addDropProjectedAkts}, eklenen: ${course.akts}).`;
					setTimeout(() => (dropError = null), 5000);
					return;
				}
				await postDouDraftEnrollments(token, [course.id], 'add_drop', {
					exclude_drop_enrollment_ids: [...markedDrop]
				});
			}
			await loadPage();
		} catch (e: unknown) {
			dropError = e instanceof Error ? e.message : 'İşlem yapılamadı.';
		}
	}

	function toggleAddDropCart(course: AvailableCourse) {
		void toggleAddDropCartAsync(course);
	}

	async function submitAddDropPackage() {
		if (!addDropDraftRows.length && !markedDrop.size) return;
		dropSubmitting = true;
		dropSuccess = null;
		dropError = null;
		const token = localStorage.token ?? null;
		try {
			await submitDouStudentSchedule(token, undefined, {
				flow: 'add_drop',
				enrollment_ids_to_drop: [...markedDrop]
			});
			const adds = addDropDraftRows
				.map((e) => `• + ${e.course_code} (${e.akts} AKTS)`)
				.join('\n');
			const drops = [...markedDrop]
				.map((id) => enrollments.find((x) => x.id === id))
				.filter(Boolean)
				.map((e) => `• − ${e!.course_code}`)
				.join('\n');
			const advisorRid2 = await resolveAdvisorReceiverUserId(token);
			if (advisorRid2) {
				await sendDouMessageApi(token, {
					receiver_user_id: advisorRid2,
					receiver_name: 'Danışmanım',
					receiver_type: 'akademisyen',
					subject: 'Ders ekle-bırak — Danışman onayı',
					body: `Sayın Danışmanım,\n\nDers değişiklik talebimi danışman onayınıza gönderdim.\n\n${adds || '(yeni ders yok)'}\n\n${drops || '(bırakma yok)'}\n\nPlanlanan dönem yükü: ${addDropProjectedAkts} AKTS.\n\nSaygılarımla`
				}).catch(() => {});
			}
			dropSuccess =
				'Talebiniz danışman onayına iletildi; taslak eklemeler ve bırakma işaretleri geçici olarak kilitlendi.';
			markedDrop = new Set();
			await loadPage();
		} catch (e: unknown) {
			dropError = e instanceof Error ? e.message : 'Gönderilemedi.';
		} finally {
			dropSubmitting = false;
		}
	}

	async function submitDocRequest() {
		docSubmitting = true;
		docSuccess = null;
		docError = null;
		const token = localStorage.token ?? null;
		try {
			await createDouDocumentRequest(token, { ...docForm });
			docSuccess = 'Belge talebiniz alındı.';
			const r = await getDouStudentDocumentRequests(token);
			docRequests = r.requests;
		} catch (e: unknown) {
			docError = e instanceof Error ? e.message : 'Hata.';
		} finally {
			docSubmitting = false;
		}
	}

	async function sendMessage() {
		composeSending = true;
		composeSuccess = null;
		composeError = null;
		const token = localStorage.token ?? null;
		try {
			if (!token) {
				composeError = 'Giriş yapmanız gerekiyor.';
				return;
			}
			const rid = await resolveAdvisorReceiverUserId(token);
			if (!rid) {
				composeError = 'Danışman kaydı bulunamadı; mesaj gönderilemiyor.';
				return;
			}
			await sendDouMessageApi(token, {
				receiver_user_id: rid,
				receiver_name: composeForm.receiver_name,
				receiver_type: composeForm.receiver_type,
				subject: composeForm.subject,
				body: composeForm.body
			});
			composeSuccess = 'Mesajınız gönderildi.';
			composeForm = {
				subject: '',
				body: '',
				receiver_name: 'Danışmanım',
				receiver_type: 'akademisyen'
			};
			showCompose = false;
			const r = await getDouSent(token);
			sentMsgs = r.messages;
		} catch (e: unknown) {
			composeError = e instanceof Error ? e.message : 'Hata.';
		} finally {
			composeSending = false;
		}
	}

	function changePassword() {
		pwBusy = true;
		pwErr = null;
		pwOk = null;
		setTimeout(() => {
			if (!pwForm.current_password || !pwForm.new_password) {
				pwErr = 'Tüm alanlar zorunludur.';
			} else if (pwForm.new_password !== pwForm.confirm_password) {
				pwErr = 'Şifreler eşleşmiyor.';
			} else if (pwForm.new_password.length < 8) {
				pwErr = 'En az 8 karakter olmalı.';
			} else if (!/[A-Z]/.test(pwForm.new_password)) {
				pwErr = 'En az 1 büyük harf içermeli.';
			} else if (!/\d/.test(pwForm.new_password)) {
				pwErr = 'En az 1 rakam içermeli.';
			} else {
				pwOk = 'Şifreniz başarıyla güncellendi.';
				pwForm = { current_password: '', new_password: '', confirm_password: '' };
			}
			pwBusy = false;
		}, 400);
	}

	const GRADE_COLOR: Record<string, string> = {
		'A+': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
		A: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
		'B+': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
		B: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
		'C+': 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
		C: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
		'D+': 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
		D: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
		F: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
		M: 'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300',
		S: 'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300',
		DZ: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
		G: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
		K: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
		TKR: 'bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300',
		AA: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
		BA: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
		BB: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
		CB: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
		CC: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
		DC: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
		DD: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
		FD: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
		FF: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
	};

	$: aktsBarDenom = Math.max(1, aktsMax);
</script>

<svelte:head><title>OBS — {pageTitle}</title></svelte:head>

<div class="relative">
	<div class="space-y-4">
		<!-- ——— Başlık ——— -->
		<div
			class="flex min-w-0 items-center justify-between rounded-xl border border-black/10 bg-white px-4 py-3 shadow-sm dark:border-white/10 dark:bg-white/5 sm:px-5 sm:py-3.5"
		>
			<div class="min-w-0 pr-2">
				<h1 class="break-words text-base font-bold text-slate-800 dark:text-slate-100">{pageTitle}</h1>
				<p class="mt-0.5 break-all text-[11px] text-slate-400 sm:break-words">{activePath}</p>
			</div>
		</div>

		<!-- ——— Tarih Kapalı Overlay ——— -->
		{#if (apiKey === 'ders-kayit' || apiKey === 'ders-ekle') && !isWindowOpen && !loading}
			<div class="relative overflow-hidden rounded-2xl border border-amber-200 bg-white p-12 text-center shadow-lg dark:border-amber-900/40 dark:bg-slate-900">
				<div class="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(245,158,11,0.05),transparent)]"></div>
				
				<div class="relative z-10">
					<div class="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-amber-100 text-4xl dark:bg-amber-900/30">
						🗓️
					</div>
					
					<h2 class="text-2xl font-black text-slate-800 dark:text-slate-100">
						{apiKey === 'ders-kayit' ? 'Ders Kayıt' : 'Ders Ekle-Bırak'} Penceresi Kapalı
					</h2>
					
					<p class="mx-auto mt-4 max-w-md text-slate-600 dark:text-slate-400">
						Mevcut dönem (<span class="font-bold text-slate-800 dark:text-slate-200">{activeTerm?.name}</span>) 
						için işlem süreci henüz başlamadı veya sona erdi.
					</p>

					<div class="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
						<div class="rounded-xl border border-black/5 bg-slate-50 p-4 dark:border-white/5 dark:bg-white/5">
							<div class="text-[10px] font-bold uppercase tracking-widest text-slate-400">Başlangıç</div>
							<div class="mt-1 font-bold text-slate-700 dark:text-slate-200">
								{apiKey === 'ders-kayit' ? activeTerm?.registration_start : activeTerm?.add_drop_start}
							</div>
						</div>
						<div class="rounded-xl border border-black/5 bg-slate-50 p-4 dark:border-white/5 dark:bg-white/5">
							<div class="text-[10px] font-bold uppercase tracking-widest text-slate-400">Bitiş</div>
							<div class="mt-1 font-bold text-slate-700 dark:text-slate-200">
								{apiKey === 'ders-kayit' ? activeTerm?.registration_end : activeTerm?.add_drop_end}
							</div>
						</div>
					</div>

					<button 
						on:click={() => window.history.back()}
						class="mt-10 rounded-xl bg-slate-800 px-8 py-3 text-sm font-bold text-white hover:bg-slate-700 transition-all dark:bg-sky-600 dark:hover:bg-sky-500"
					>
						Geri Dön
					</button>
				</div>
			</div>
		{/if}

		<!-- ——— Yükleniyor / Hata ——— -->
		{#if loading}
			<div
				class="flex items-center justify-center rounded-xl border border-black/10 bg-white p-12 dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="h-5 w-5 animate-spin rounded-full border-2 border-sky-500 border-t-transparent"
				></div>
				<span class="ml-3 text-sm text-slate-400">Yükleniyor…</span>
			</div>
		{:else if loadErr}
			<div
				class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900/40 dark:bg-amber-950/30"
			>
				<div class="text-sm font-semibold text-amber-900 dark:text-amber-100">Bağlantı hatası</div>
				<div class="mt-1 text-xs text-amber-700 dark:text-amber-200">{loadErr}</div>
				<div class="mt-2 text-[11px] text-amber-600 dark:text-amber-300">
					Backend yeniden başlatılması gerekiyor olabilir.
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- PROFİL                                                           -->
			<!-- ================================================================ -->
		{:else if apiKey === 'profile' && profile}
			{#if !profileEdit}
				{#if profile._obs_profile_missing}
					<div
						class="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-100"
					>
						<div class="font-semibold">Öğrenci özlük kaydı eksik</div>
						<p class="mt-1 text-xs leading-relaxed opacity-90">
							Özlük kaydınız bulunamadı. <strong>OBS Yönetim → Kullanıcı Yönetimi</strong>’nde hesabınız
							için <strong>Özlük</strong> ile kayıt oluşturun veya hesabı (öğrenci numarası + bölüm ile)
							<strong>+ Kullanıcı Ekle</strong> üzerinden oluşturun. Open WebUI’nin genel “kullanıcı ekle”
							ekranı özlük oluşturmaz.
						</p>
					</div>
				{/if}
				<!-- ── Hero kartı ────────────────────────────────────── -->
				<div
					class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-slate-900"
				>
					<!-- Gradient banner -->
					<div class="h-24 bg-gradient-to-r from-sky-500 via-indigo-500 to-violet-500"></div>

					<div class="relative px-6 pb-6">
						<!-- Avatar -->
						<div
							class="absolute -top-8 left-6 flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 to-indigo-600 text-2xl font-black text-white shadow-lg ring-4 ring-white dark:ring-slate-900"
						>
							{(profile.full_name ?? profile.email ?? 'Ö').charAt(0).toUpperCase()}
						</div>

						<!-- Ad + düzenle -->
						<div class="flex flex-col gap-3 pt-10 sm:flex-row sm:items-start sm:justify-between sm:gap-0">
							<div class="min-w-0">
								<div class="break-words text-xl font-bold text-slate-900 dark:text-slate-100">
									{profile.full_name ?? profile.email}
								</div>
								<div class="mt-0.5 text-sm text-slate-500">
									{profile.student_no} · {profile.faculty_name ?? profile.department_name}
								</div>
								<div class="mt-0.5 text-xs text-slate-400">
									{profile.department_name} — {profile.program ?? 'Lisans'} · {profile.class_level}.
									Sınıf
								</div>
							</div>
							<button
								on:click={() => {
									profileEdit = true;
									profileSaved = false;
									profileForm = {
										full_name: profile.full_name ?? '',
										phone: (profile as Record<string, string>).phone ?? '',
										address: (profile as Record<string, string>).address ?? '',
										emergency_contact: (profile as Record<string, string>).emergency_contact ?? '',
										emergency_phone: (profile as Record<string, string>).emergency_phone ?? ''
									};
								}}
								type="button"
								class="shrink-0 self-start sm:self-auto mt-1 flex items-center gap-1.5 rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10 transition-colors"
							>
								<svg
									class="h-3.5 w-3.5 text-slate-400"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2"
									><path
										d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
									/></svg
								>
								Düzenle
							</button>
						</div>

						<!-- GNO / DNO / AKTS stat bar -->
						{#if true}
							{@const agno = (profile as unknown as Record<string, number>).gpa ?? 0}
							{@const dno = (profile as unknown as Record<string, number>).dno ?? 0}
							{@const tamamAkts =
								(profile as unknown as Record<string, number>).completed_akts ?? 0}
							{@const toplamAkts =
								(profile as unknown as Record<string, number>).total_akts_required ?? 120}
							<div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
								{#each [{ lbl: 'AGNO', val: agno.toFixed(2), sub: 'Kümülatif', color: agno >= 3.0 ? 'text-emerald-600 dark:text-emerald-400' : agno >= 2.0 ? 'text-sky-600 dark:text-sky-400' : 'text-red-500' }, { lbl: 'DNO', val: dno.toFixed(2), sub: 'Bu Dönem', color: dno >= 3.0 ? 'text-emerald-600 dark:text-emerald-400' : dno >= 2.0 ? 'text-sky-600 dark:text-sky-400' : 'text-red-500' }, { lbl: 'AKTS', val: tamamAkts.toString(), sub: `/ ${toplamAkts}`, color: 'text-slate-800 dark:text-slate-100' }, { lbl: 'Durum', val: profile.status === 'active' ? 'Aktif' : (profile.status ?? 'Aktif'), sub: profile.is_financially_eligible ? 'Mali uygun' : 'Borç var', color: profile.status === 'active' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500' }] as st}
									<div
										class="rounded-xl border border-black/8 bg-slate-50 px-4 py-3 dark:border-white/8 dark:bg-white/5"
									>
										<div class="text-[10px] font-bold uppercase tracking-widest text-slate-400">
											{st.lbl}
										</div>
										<div class="mt-1 text-xl font-black {st.color}">{st.val}</div>
										<div class="text-[10px] text-slate-400">{st.sub}</div>
									</div>
								{/each}
							</div>
						{/if}

						<!-- İletişim bilgileri -->
						<div
							class="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-black/8 bg-black/5 dark:border-white/8 dark:bg-white/10 sm:grid-cols-3"
						>
							{#each [['E-posta', profile.email], ['Kayıt Tarihi', profile.enrollment_date ?? '—'], ['Bölüm', profile.department_name]] as [lbl, val]}
								<div class="bg-white px-4 py-3 dark:bg-slate-900">
									<div class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
										{lbl}
									</div>
									<div
										class="mt-0.5 break-words text-sm font-medium text-slate-800 dark:text-slate-100 sm:truncate"
										title={typeof val === 'string' ? val : ''}
									>
										{val}
									</div>
								</div>
							{/each}
						</div>

						{#if profileSaved}
							<div
								class="mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
							>
								Profil güncellendi.
							</div>
						{/if}
					</div>
				</div>
			{:else}
				<!-- ── Düzenleme formu ──────────────────────────────── -->
				<div
					class="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-slate-900"
				>
					<div class="border-b border-black/5 px-6 py-4 dark:border-white/10">
						<div class="text-sm font-bold text-slate-700 dark:text-slate-200">
							Kişisel Bilgileri Düzenle
						</div>
						<div class="text-xs text-slate-400">
							Öğrenci no, bölüm ve program bilgileri değiştirilemez.
						</div>
					</div>
					<div class="px-6 py-5">
						{#if profileError}
							<div
								class="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
							>
								{profileError}
							</div>
						{/if}
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
							{#each [{ lbl: 'Ad Soyad', field: 'full_name', type: 'text', ph: 'Adınız ve soyadınız' }, { lbl: 'Cep Telefonu', field: 'phone', type: 'tel', ph: '0532 XXX XX XX' }, { lbl: 'Adres', field: 'address', type: 'text', ph: 'İkamet adresiniz' }, { lbl: 'Acil İrtibat (Ad)', field: 'emergency_contact', type: 'text', ph: 'Anne / Baba / Eş' }, { lbl: 'Acil İrtibat (Tel)', field: 'emergency_phone', type: 'tel', ph: '0532 XXX XX XX' }] as fld}
								<label class="block">
									<div class="mb-1.5 text-xs font-semibold text-slate-500">{fld.lbl}</div>
									<input
										bind:value={profileForm[fld.field as keyof typeof profileForm]}
										type={fld.type}
										placeholder={fld.ph}
										class="w-full rounded-xl border border-black/10 bg-slate-50 px-3.5 py-2.5 text-sm outline-none transition focus:border-sky-400 focus:bg-white focus:ring-2 focus:ring-sky-400/20 dark:border-white/10 dark:bg-white/5 dark:focus:border-sky-500 dark:focus:bg-white/10"
									/>
								</label>
							{/each}
						</div>

						<!-- Salt okunur alanlar (gri) -->
						<div
							class="mt-5 rounded-xl border border-black/8 bg-slate-50 p-4 dark:border-white/8 dark:bg-white/5"
						>
							<div class="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-400">
								Değiştirilemeyen Bilgiler
							</div>
							<div class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
								{#each [['Öğrenci No', profile.student_no], ['Bölüm', profile.department_name], ['Program', profile.program ?? 'Lisans']] as [l, v]}
									<div>
										<span class="text-xs text-slate-400">{l}</span>
										<div class="font-medium text-slate-600 dark:text-slate-300">{v}</div>
									</div>
								{/each}
							</div>
						</div>

						<div class="mt-5 flex gap-3">
							<button
								on:click={saveProfile}
								disabled={profileSaving}
								type="button"
								class="flex items-center gap-2 rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
							>
								{#if profileSaving}<div
										class="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
									></div>{/if}
								{profileSaving ? 'Kaydediliyor…' : 'Kaydet'}
							</button>
							<button
								on:click={() => {
									profileEdit = false;
									profileError = null;
								}}
								type="button"
								class="rounded-xl border border-black/10 px-5 py-2.5 text-sm font-medium hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5 transition-colors"
							>
								İptal
							</button>
						</div>
					</div>
				</div>
			{/if}
		{:else if apiKey === 'profile'}
			<div
				class="rounded-xl border border-black/10 bg-white px-5 py-10 text-center text-sm text-slate-500 shadow-sm dark:border-white/10 dark:bg-white/5 dark:text-slate-400"
			>
				<p class="font-medium text-slate-700 dark:text-slate-200">Öğrenci profili bulunamadı</p>
				<p class="mt-2 text-xs">
					Özlük kaydı yoksa yönetimden profil oluşturulmalıdır.
				</p>
			</div>

			<!-- ================================================================ -->
			<!-- AKADEMİK TAKVİM                                                  -->
			<!-- ================================================================ -->
		{:else if apiKey === 'calendar'}
			<div class="space-y-4">
				<div class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-2 text-xs font-bold tracking-widest text-slate-400 dark:text-slate-500">
						TAKVİM DOSYALARI
					</div>
					{#if calendarDocs.length}
						<div class="divide-y divide-black/5 overflow-hidden rounded-xl border border-black/10 dark:divide-white/10 dark:border-white/10">
							{#each calendarDocs as f}
								{@const title = String((f.meta?.display_name ?? '') || f.filename)}
								<a
									class="flex items-center gap-3 bg-white px-3 py-3 text-sm hover:bg-slate-50 dark:bg-transparent dark:hover:bg-white/5"
									href={`${WEBUI_API_BASE_URL}/files/${f.id}/content`}
									target="_blank"
									rel="noreferrer"
								>
									<div class="shrink-0 rounded-lg border border-black/10 bg-slate-50 px-2 py-2 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-200">
										<span class="text-xs font-black">PDF</span>
									</div>
									<div class="min-w-0 flex-1">
										<div class="truncate font-semibold text-slate-800 dark:text-slate-100">
											{title}
										</div>
										<div class="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
											{f.size ? fmtBytes(f.size) : 'PDF'}
										</div>
									</div>
									<div class="shrink-0 rounded-lg border border-black/10 px-3 py-1.5 text-[11px] font-bold text-slate-600 dark:border-white/10 dark:text-slate-200">
										İndir
									</div>
								</a>
							{/each}
						</div>
					{:else}
						<div class="py-6 text-center text-sm text-slate-400">
							Bu dönem için takvim dosyası yok.
						</div>
					{/if}
				</div>
			</div>
		{:else if apiKey === 'terms' && terms.length}
			<div
				class="-mx-1 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5 sm:mx-0"
			>
				<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
					Listeyi yatay kaydırarak tüm sütunları görebilirsiniz.
				</p>
				<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
					<div class="min-w-[520px]">
				<div
					class="grid grid-cols-5 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
				>
					<div class="col-span-2 min-w-0 break-words">Dönem</div>
					<div>Yıl</div>
					<div class="whitespace-nowrap">Başlangıç</div>
					<div class="whitespace-nowrap">Bitiş</div>
				</div>
				{#each terms as t}
					<div
						class="grid grid-cols-5 border-t border-black/5 px-5 py-3.5 text-sm dark:border-white/10 {t.is_active
							? 'bg-sky-50/40 dark:bg-sky-900/10'
							: ''}"
					>
						<div class="col-span-2 min-w-0 font-medium break-words">
							{t.name}
							{#if t.is_active}<span
									class="ml-2 inline-flex shrink-0 rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
									>Aktif</span
								>{/if}
						</div>
						<div class="text-slate-500">{t.academic_year}</div>
						<div class="whitespace-nowrap text-slate-500">{t.starts_at}</div>
						<div class="whitespace-nowrap text-slate-500">{t.ends_at}</div>
					</div>
				{/each}
					</div>
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- DANIŞMAN                                                          -->
			<!-- ================================================================ -->
		{:else if apiKey === 'advisor' && advisor?.advisor}
			<div
				class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5 sm:p-6"
			>
				<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-5">
					<div
						class="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-400 to-indigo-600 text-2xl font-bold text-white shadow"
					>
						{advisor.advisor.name.charAt(0)}
					</div>
					<div class="min-w-0 flex-1">
						<div class="break-words text-xl font-bold">{advisor.advisor.name}</div>
						{#if advisor.advisor.title}<div class="mt-0.5 text-sm text-slate-500">
								{advisor.advisor.title}
							</div>{/if}
					</div>
				</div>

				<div
					class="mt-5 flex gap-4 rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/90 to-white p-4 dark:border-indigo-900/35 dark:from-indigo-950/25 dark:to-white/5"
				>
					<div
						class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-700 shadow-inner dark:bg-indigo-900/45 dark:text-indigo-100"
						aria-hidden="true"
					>
						<svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="1.75"
								d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
							/>
						</svg>
					</div>
					<div class="min-w-0 flex-1">
						<div class="text-xs font-bold uppercase tracking-wide text-indigo-800/70 dark:text-indigo-200/80">
							Danışmanlık / ofis görüşme saatleri
						</div>
						<div class="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-800 dark:text-slate-100">
							{#if advisor.advisor.consulting_hours?.trim()}
								{advisor.advisor.consulting_hours}
							{:else}
								<span class="text-slate-400 dark:text-slate-500"
									>Danışmanınız henüz bu bilgiyi paylaşmadı.</span
								>
							{/if}
						</div>
					</div>
				</div>

				<div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
					{#each [['E-posta', advisor.advisor.email, true], ['Oda', advisor.advisor.office ?? '—', false], ['Telefon', advisor.advisor.phone ?? '—', false], ['Bölüm', advisor.advisor.department_name ?? '—', false]] as [lbl, val, isEmail]}
						<div
							class="rounded-xl border border-black/5 bg-slate-50 px-4 py-3 dark:border-white/5 dark:bg-white/5"
						>
							<div class="text-xs font-semibold text-slate-400">{lbl}</div>
							{#if isEmail}
								<a
									href="mailto:{val}"
									class="mt-1 block text-sm font-medium text-sky-600 hover:underline dark:text-sky-400"
									>{val}</a
								>
							{:else}
								<div class="mt-1 text-sm font-medium">{val}</div>
							{/if}
						</div>
					{/each}
				</div>
				<div class="mt-4 flex gap-2">
					<button
						on:click={() => (showCompose = true)}
						type="button"
						class="flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
					>
						Mesaj Gönder
					</button>
				</div>
			</div>
		{:else if apiKey === 'advisor' && advisor && !advisor.advisor}
			<div
				class="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 p-8 text-center text-sm text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400"
			>
				Kayıtlı danışman bilgisi bulunamadı.
			</div>

			<!-- ================================================================ -->
			<!-- ALINAN DERSLER                                                    -->
			<!-- ================================================================ -->
		{:else if apiKey === 'enrollments'}
			<div
				class="mb-2 flex min-w-0 flex-col gap-2 rounded-xl border border-black/10 bg-white px-4 py-3 shadow-sm dark:border-white/10 dark:bg-white/5 sm:flex-row sm:items-center sm:justify-between sm:px-5 sm:py-3"
			>
				<div class="flex items-center gap-3">
					<span class="text-sm font-semibold">{enrollments.length} ders</span>
					<span
						class="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
						>{totalAkts} AKTS</span
					>
				</div>
			</div>
			<div
				class="-mx-1 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5 sm:mx-0"
			>
				<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
					Tabloyu yatay kaydırarak tüm sütunları görebilirsiniz.
				</p>
				<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
					<table class="min-w-[720px] w-full border-collapse text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="whitespace-nowrap px-4 py-3 text-left">Kod</th>
								<th class="min-w-[12rem] px-4 py-3 text-left">Ders Adı</th>
								<th class="whitespace-nowrap px-4 py-3 text-center">K</th>
								<th class="whitespace-nowrap px-4 py-3 text-center">AKTS</th>
								<th class="min-w-[8rem] px-4 py-3 text-left">Öğretim Elemanı</th>
								<th class="whitespace-nowrap px-4 py-3 text-left">Gün / Saat</th>
								<th class="whitespace-nowrap px-4 py-3 text-left">Derslik</th>
							</tr>
						</thead>
						<tbody>
							{#each enrollments as e}
								<tr
									class="border-t border-black/5 hover:bg-slate-50/50 transition-colors dark:border-white/10 dark:hover:bg-white/5"
								>
									<td
										class="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold text-slate-600 dark:text-slate-300"
										>{e.course_code}</td
									>
									<td
										class="min-w-[12rem] px-4 py-3 align-top font-medium leading-snug break-words"
										>{e.course_name}</td
									>
									<td class="whitespace-nowrap px-4 py-3 text-center text-slate-500"
										>{e.credits}</td
									>
									<td class="whitespace-nowrap px-4 py-3 text-center font-semibold">{e.akts}</td>
									<td class="max-w-[10rem] min-w-[8rem] px-4 py-3 align-top text-xs leading-snug break-words text-slate-500 sm:max-w-none"
										>{e.instructor_name ?? '—'}</td
									>
									<td class="whitespace-nowrap px-4 py-3 text-xs">{e.day_of_week ?? '—'} {e.start_time ?? ''}–{e.end_time ?? ''}</td>
									<td class="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{e.classroom ?? '—'}</td>
								</tr>
							{:else}
								<tr
									><td colspan="7" class="px-4 py-8 text-center text-sm text-slate-400"
										>Kayıtlı ders yok.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- DERS KAYIT                                                        -->
			<!-- ================================================================ -->
		{:else if apiKey === 'ders-kayit'}
			<!-- AKTS sayacı -->
			<div
				class="rounded-xl border border-sky-200 bg-sky-50 px-5 py-4 dark:border-sky-900/40 dark:bg-sky-950/20"
			>
				<div class="flex items-center justify-between text-sm">
					<span class="font-semibold break-words">{enrollmentTermLabel} — AKTS Durumu</span>
					<span class="font-bold text-sky-700 dark:text-sky-300"
						>{enrollmentScheduledAkts} / {aktsMax}</span
					>
				</div>
				<div class="mt-2 h-2 w-full overflow-hidden rounded-full bg-sky-100 dark:bg-sky-900/40">
					<div
						class="h-2 rounded-full transition-all
						{(enrollmentScheduledAkts) / aktsBarDenom > 0.9
							? 'bg-red-500'
							: enrollmentScheduledAkts / aktsBarDenom > 0.7
								? 'bg-amber-400'
								: 'bg-sky-500'}"
						style="width:{Math.min(100, (enrollmentScheduledAkts / aktsBarDenom) * 100)}%"
					></div>
				</div>
				{#if aktsLimitHint}
					<p class="mt-2 text-[11px] text-sky-800/80 dark:text-sky-200/90">{aktsLimitHint}</p>
				{/if}
			</div>

			{#if registrationLimits?.curriculum_elective_locked && (registrationLimits.curriculum_mandatory_remaining?.length ?? 0) > 0}
				{@const slotHintMandatoryRg = obsCurriculumPlacementHint(registrationLimits?.program_semester_number)}
				<div
					class="mt-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-950 dark:border-violet-900/40 dark:bg-violet-950/30 dark:text-violet-100"
				>
					<p class="mb-2 font-semibold leading-snug">
						Program yarıyılı {registrationLimits?.program_semester_number ?? '—'}
						{#if slotHintMandatoryRg}
							<span class="mt-0.5 block text-xs font-normal text-violet-900/85 dark:text-violet-200/90"
								>{slotHintMandatoryRg}</span
							>
						{/if}
					</p>
					<p class="mb-2 text-xs text-violet-900/90 dark:text-violet-200/90">
						Zorunlu dersleri ekledikten sonra seçmeli derslerinizi ekleyebilirsiniz. Aşağıda listelenen
						müfredat zorunluları bu dönem planınıza eklenmedikçe seçmeli şube seçimi sistem tarafından
						engellenir.
					</p>
					<ul class="list-disc space-y-0.5 pl-5 text-xs">
						{#each registrationLimits.curriculum_mandatory_remaining ?? [] as m}
							{@const mCsResolved = resolvedMandatoryCurriculumSemester(m, curriculumSemesterByOfferedCourseCode)}
							{@const mPl = obsCurriculumPlacementHint(mCsResolved)}
							<li class="[&::marker]:text-violet-500">
								<span class="font-mono font-semibold">{m.course_code}</span>
								— {m.course_name}
								<span class="opacity-90"> ({m.akts} AKTS)</span>{#if mPl}<span class="text-xs font-medium text-violet-900/95 dark:text-violet-300/95"> · {mPl}</span>{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if hasPendingRegistration}
				<div
					class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200"
				>
					<strong>Danışman onayında:</strong> Ders seçiminiz kilitli. Danışmanınız kesinleştirdiğinde
					kayıtlarınız <strong>Kesinleştirildi</strong> olarak görünecek; haftalık programınız güncellenir
					(<a href="/obs/ogrenci/ders-programi" class="underline font-semibold">Ders programı</a>).
				</div>
			{/if}

			<!-- ── SEÇİLEN / TASLAK DERSLER TABLOSU ── -->
			{#if registrationPickRows.length}
				<div
					class="mt-3 overflow-hidden rounded-xl border border-sky-200 bg-white shadow-sm dark:border-sky-900/30 dark:bg-sky-950/10"
				>
					<div class="bg-sky-50/80 px-5 py-2.5 border-b border-sky-100 dark:bg-sky-900/20 dark:border-sky-900/30 flex items-center justify-between">
						<span class="text-sm font-bold text-sky-900 dark:text-sky-100">Seçtiğiniz Dersler</span>
						<div class="flex items-center gap-3">
							<span class="text-[11px] font-semibold text-sky-700 dark:text-sky-400">
								{registrationPickRows.length} Ders
							</span>
							<span class="rounded-full bg-sky-200 px-2 py-0.5 text-[10px] font-black text-sky-800">
								{enrollmentScheduledAkts} AKTS
							</span>
						</div>
					</div>
					<p class="border-b border-sky-100 bg-sky-50/90 px-3 py-1.5 text-[11px] text-sky-800/80 dark:border-sky-900/30 dark:bg-sky-950/40 dark:text-sky-300/90 sm:hidden">
						Tabloyu yatay kaydırarak tüm sütunları görebilirsiniz.
					</p>
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<table class="min-w-[720px] w-full text-[13px]">
							<thead class="bg-sky-50/30 text-[11px] font-bold text-sky-600 dark:text-sky-400 uppercase tracking-wider">
								<tr>
									<th class="whitespace-nowrap px-4 py-2 text-left">Kod</th>
									<th class="whitespace-nowrap px-4 py-2 text-left">Tür</th>
									<th class="min-w-[10rem] px-4 py-2 text-left">Ders Adı</th>
									<th class="whitespace-nowrap px-4 py-2 text-center">AKTS</th>
									<th class="whitespace-nowrap px-4 py-2 text-center">Durum</th>
									<th class="min-w-[8rem] px-4 py-2 text-left">Öğr. Elemanı</th>
									<th class="whitespace-nowrap px-4 py-2 text-right"></th>
								</tr>
							</thead>
							<tbody class="divide-y divide-sky-50 dark:divide-sky-900/20">
								{#each registrationPickRows as e}
									<tr class="hover:bg-sky-50/20 transition-colors">
										<td class="whitespace-nowrap px-4 py-2.5 font-mono font-bold text-sky-700 dark:text-sky-300">{e.course_code}</td>
										<td class="whitespace-nowrap px-4 py-2.5 text-xs font-medium text-slate-600 dark:text-slate-400">{curriculumKindColumnLabel(e)}</td>
										<td class="min-w-[10rem] max-w-[22rem] px-4 py-2.5 font-medium leading-snug break-words text-slate-700 dark:text-slate-200">{e.course_name}</td>
										<td class="whitespace-nowrap px-4 py-2.5 text-center font-bold">{e.akts}</td>
										<td class="px-4 py-2.5 text-center">
											{#if e.status === 'active'}
												<span class="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">KAYITLI</span>
											{:else if e.status === 'pending'}
												<span class="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">ONAY BEKLİYOR</span>
											{:else}
												<span class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">TASLAK</span>
											{/if}
										</td>
										<td class="min-w-[8rem] px-4 py-2.5 text-xs leading-snug break-words text-slate-500 dark:text-slate-400">{e.instructor_name ?? '—'}</td>
										<td class="whitespace-nowrap px-4 py-2.5 text-right">
											{#if e.status === 'draft' && !hasPendingRegistration}
												<button
													on:click={() => removeDraftEnrollmentRow(e.id)}
													class="text-red-500 hover:text-red-700 p-1"
													title="Dersi sepetten çıkar"
												>
													<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
												</button>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			{/if}

			<!-- Sepet / Gönder -->
			<div class="mt-3">
				{#if enrollSuccess}
					<div
						class="mb-3 rounded-lg bg-emerald-100 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
					>
						{enrollSuccess}
					</div>
				{/if}
				{#if enrollError}
					<div
						class="mb-3 rounded-lg bg-red-100 px-3 py-2 text-sm text-red-700 dark:bg-red-900/40 dark:text-red-200"
					>
						{enrollError}
					</div>
				{/if}
				<button
					on:click={finalizeEnrollment}
					disabled={enrollSubmitting || hasPendingRegistration}
					type="button"
					class="flex w-full items-center justify-center gap-2 rounded-xl bg-sky-600 py-2.5 text-sm font-bold text-white hover:bg-sky-500 disabled:opacity-50 transition-colors"
				>
					{#if enrollSubmitting}
						<div
							class="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
						></div>
					{/if}
					{enrollSubmitting
						? 'Gönderiliyor…'
						: enrollmentScheduledAkts < (registrationLimits?.akts_min ?? 30)
							? `Min. ${(registrationLimits?.akts_min ?? 30)} AKTS gerekli`
							: 'Danışman onayına gönder'}
				</button>
			</div>

			<!-- Açılan dersler tablosu (ekle-bırak ile aynı API süzümü + müfredat yer tutucuları) -->
			<div
				class="mt-3 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="flex flex-wrap items-start justify-between gap-2 border-b border-black/5 px-4 py-3 dark:border-white/10 sm:items-center sm:px-5"
				>
					<div class="text-sm font-bold text-slate-600 dark:text-slate-300">Açılan Dersler</div>
					<div class="flex flex-wrap items-center gap-3">
						<label class="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-2">
							<span class="shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400"
								>Sınıf ve yarıyıl</span
							>
							<select
								bind:value={catalogSectionFilterKey}
								class="max-w-[16rem] rounded-lg border border-black/10 bg-white px-2 py-1.5 text-xs font-medium text-slate-800 shadow-sm dark:border-white/10 dark:bg-white/10 dark:text-slate-100"
							>
								{#each catalogSlotFilterOptions as opt (opt.key)}
									<option value={opt.key}>{opt.label}</option>
								{/each}
							</select>
						</label>
						<div class="shrink-0 text-xs text-slate-500 dark:text-slate-400">
							<span
								>{catalogSectionsCountSummary(
									filteredAvailableCourses.length,
									availableCourses.length,
									registrationOfferPlaceholderRowsMeta > 0
										? {
												realSections: registrationRealSectionRowCount,
												placeholders: registrationOfferPlaceholderRowsMeta
											}
										: undefined
								)}</span
							>
						</div>
					</div>
				</div>
				<p
					class="border-b border-black/5 bg-slate-50/90 px-4 py-2 text-[11px] leading-snug text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:px-5"
				>
					Derslerinizi sınıf ve yarıyılınıza göre listeleyebilirsiniz. Bölümünüzdeki tüm açılan şubeleri
					görmek için listeden <strong>Tümü — tüm sınıflar ve yarıyıllar</strong> seçeneğini kullanın.
					Şubesi tanımlı dersler kayıt için seçilebilir; şubesiz satırlar yalnızca müfredat planı
					bilgisini gösterir.
				</p>
				{#if registrationSectionsEmptyHint}
					<p
						class="border-b border-black/5 bg-amber-50/90 px-4 py-2 text-left text-[11px] leading-snug text-amber-950 dark:border-amber-500/35 dark:bg-amber-950/35 dark:text-amber-50 sm:px-5"
					>
						{registrationSectionsEmptyHint}
					</p>
				{/if}
				<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
					Tabloyu yatay kaydırarak tüm sütunları görebilirsiniz.
				</p>
				{#if !filteredAvailableCourses.length}
					<div
						class="space-y-3 px-5 py-6 text-center text-sm leading-relaxed text-slate-500 dark:text-slate-400"
					>
						{#if availableCourses.length && catalogFilterActive}
							<p>
								Seçtiğiniz <strong>{catalogSlotLabelFromKey(catalogSectionFilterKey)}</strong> için
								açılmış şube bulunmuyor.
							</p>
							<button
								type="button"
								class="text-xs font-semibold text-sky-600 underline hover:text-sky-700 dark:text-sky-400"
								on:click={() => (catalogSectionFilterKey = 'all')}
								>Tüm açılan şubeleri listele ({availableCourses.length})</button
							>
						{:else}
							<p>Açılan ders bulunamadı.</p>
							{#if registrationSectionsInTermTotal !== null || registrationSectionsQueryRowsStudent !== null}
								<p class="text-[11px] leading-snug text-slate-400">
									Dönem öbeğinde toplam
									<span class="font-mono text-slate-500 dark:text-slate-300">açık şube</span>:
									<strong>{registrationSectionsInTermTotal ?? '—'}</strong>
									· Uygun şube satırı (öğrenci sorgusu):
									<strong>{registrationSectionsQueryRowsStudent ?? '—'}</strong>
								</p>
							{/if}
						{/if}
					</div>
				{:else}
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<table class="min-w-[1040px] w-full text-sm">
							<thead
								class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								<tr>
									<th class="whitespace-nowrap px-4 py-3 text-left">Kod</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Tür</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Sınıf</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Yarıyıl</th>
									<th class="min-w-[11rem] px-4 py-3 text-left">Ders Adı</th>
									<th class="whitespace-nowrap px-4 py-3 text-center">AKTS</th>
									<th class="min-w-[8rem] px-4 py-3 text-left">Öğr. Elemanı</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Gün/Saat</th>
									<th class="whitespace-nowrap px-4 py-3 text-center">Kontenjan</th>
									<th class="whitespace-nowrap px-4 py-3 text-center"></th>
								</tr>
							</thead>
							<tbody>
								{#each filteredAvailableCourses as c}
									{@const ophRg = !!(c as AvailableCourse & { offer_placeholder?: boolean }).offer_placeholder}
									{@const inCart =
										!ophRg &&
										enrollments.some(
											(x) =>
												x.status === 'draft' &&
												x.section_id === c.id &&
												(x.enrollment_reason || '') !== 'add_drop'
										)}
									{@const full = !ophRg && c.enrolled >= c.capacity}
									<tr
										class="border-t border-black/5 dark:border-white/10 {ophRg
											? 'bg-amber-50/35 dark:bg-amber-950/15'
											: ''} {inCart
											? 'bg-sky-50/50 dark:bg-sky-900/10'
											: 'hover:bg-slate-50/50 dark:hover:bg-white/5'} transition-colors"
									>
										<td class="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold text-slate-500"
											>{c.course_code}</td
										>
										<td class="whitespace-nowrap px-4 py-3 text-xs font-medium text-slate-600 dark:text-slate-400">{curriculumKindColumnLabel(c)}</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{c.catalog_class_label ?? '—'}</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{c.catalog_half_label ?? '—'}</td>
										<td class="min-w-[12rem] max-w-[22rem] px-4 py-3 text-sm font-semibold leading-snug break-words text-slate-900 dark:text-slate-50">
											{c.course_name}
										</td>
										<td class="whitespace-nowrap px-4 py-3 text-center font-semibold">{c.akts}</td>
										<td class="min-w-[8rem] px-4 py-3 text-xs leading-snug break-words text-slate-500">{ophRg ? '—' : c.instructor_name}</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs">{ophRg ? '—' : `${c.day_of_week ?? ''} ${c.start_time ?? ''}–${c.end_time ?? ''}`.trim() || '—'}</td>
										<td
											class="px-4 py-3 text-center text-xs {full ? 'text-red-500' : 'text-slate-500'}"
										>
											{c.enrolled}/{c.capacity}
											{#if full}<span
													class="ml-1 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-900/40 dark:text-red-300"
													>Dolu</span
												>{/if}
										</td>
										<td class="whitespace-nowrap px-4 py-3 text-center align-middle">
											{#if !String(c.id || '').trim()}
												<button
													type="button"
													on:click={() => toggleCart(c)}
													class="inline-flex shrink-0 items-center justify-center rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20 whitespace-nowrap"
													title="Şube seçilebilmesi için şube kaydı gerekir; yine de denediğinizde sistem uyarısı alırsınız."
												>
													Ders ekle
												</button>
											{:else if ophRg}
												<button
													type="button"
													on:click={() => toggleCart(c)}
													class="inline-flex shrink-0 items-center justify-center rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20 whitespace-nowrap"
													title="Bu satır OBS’te şubesiz görünüyor; eklemeden önce şube oluşturulmalıdır."
												>
													Ders ekle
												</button>
											{:else if full && !inCart}
												<span class="text-xs text-slate-300">—</span>
											{:else if hasPendingRegistration}
												<span class="text-xs text-slate-400" title="Liste kilitli">Kilitli</span>
											{:else}
												<button
													type="button"
													on:click={() => toggleCart(c)}
													class="inline-flex shrink-0 items-center justify-center rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors whitespace-nowrap
													{inCart
														? 'bg-sky-100 text-sky-700 ring-1 ring-sky-300 dark:bg-sky-900/40 dark:text-sky-300'
														: 'bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20'}"
												>
													{inCart ? 'Taslakta' : 'Ders ekle'}
												</button>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<!-- ================================================================ -->
			<!-- DERS EKLE / BIRAK                                                 -->
			<!-- ================================================================ -->
		{:else if apiKey === 'ders-ekle'}
			<p class="mb-2 text-xs text-slate-500">Dönem: {addDropTermLabel}</p>
			<div
				class="mb-3 rounded-lg border border-sky-100 bg-sky-50/80 px-4 py-2 text-xs text-sky-900 dark:border-sky-900/40 dark:bg-sky-950/30 dark:text-sky-200"
			>
				{addDropAktsRuleHint}
			</div>
			{#if registrationLimits?.curriculum_elective_locked && (registrationLimits.curriculum_mandatory_remaining?.length ?? 0) > 0}
				{@const slotHintMandatoryAd = obsCurriculumPlacementHint(registrationLimits?.program_semester_number)}
				<div
					class="mb-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-950 dark:border-violet-900/40 dark:bg-violet-950/30 dark:text-violet-100"
				>
					<p class="mb-2 font-semibold leading-snug">
						Program yarıyılı {registrationLimits?.program_semester_number ?? '—'}
						{#if slotHintMandatoryAd}
							<span class="mt-0.5 block text-xs font-normal text-violet-900/85 dark:text-violet-200/90"
								>{slotHintMandatoryAd}</span
							>
						{/if}
					</p>
					<p class="mb-2 text-xs text-violet-900/90 dark:text-violet-200/90">
						Zorunlu dersleri ekledikten sonra seçmeli derslerinizi ekleyebilirsiniz. Müfredat
						zorunlularınızı bu dönem planınıza eklemeden seçmeli şube seçemezsiniz.
					</p>
					<ul class="list-disc space-y-0.5 pl-5 text-xs">
						{#each registrationLimits.curriculum_mandatory_remaining ?? [] as m}
							{@const mCsResolvedAd = resolvedMandatoryCurriculumSemester(m, curriculumSemesterByOfferedCourseCode)}
							{@const mPlAd = obsCurriculumPlacementHint(mCsResolvedAd)}
							<li class="[&::marker]:text-violet-500">
								<span class="font-mono font-semibold">{m.course_code}</span>
								— {m.course_name}
								<span class="opacity-90"> ({m.akts} AKTS)</span>{#if mPlAd}<span class="text-xs font-medium text-violet-900/95 dark:text-violet-300/95"> · {mPlAd}</span>{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			<div
				class="rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="flex flex-wrap items-start justify-between gap-2 border-b border-black/5 px-4 py-3 dark:border-white/10 sm:items-center sm:px-5"
				>
					<div>
						<span class="text-sm font-semibold">
							{enrollments.filter((e) => e.status === 'active').length} aktif ders
						</span>
						<span class="ml-2 text-xs text-slate-400">{totalAkts} AKTS (aktif)</span>
						{#if addDropDraftRows.length}
							<span class="ml-2 text-xs font-medium text-sky-600 dark:text-sky-400"
								>+{addDropDraftRows.length} taslak (eklenecek)</span
							>
						{/if}
					</div>
					{#if addDropDraftRows.length || markedDrop.size}
						<button
							on:click={submitAddDropPackage}
							disabled={dropSubmitting || hasPendingAddDrop || !addDropAktsOk}
							type="button"
							class="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-sky-500 disabled:opacity-50 transition-colors"
						>
							{dropSubmitting
								? 'Gönderiliyor…'
								: hasPendingAddDrop
									? 'Talep işlemde'
									: !addDropAktsBoundsOk
										? 'AKTS aralığı uygun değil'
										: 'Danışman onayına gönder'}
						</button>
					{/if}
				</div>

				{#if hasPendingAddDrop}
					<div
						class="mt-0 border-b border-amber-100 bg-amber-50/80 px-5 py-2 text-xs text-amber-800 dark:border-amber-900/30 dark:bg-amber-950/30 dark:text-amber-200"
					>
						Ders değişiklik talebiniz danışman onayında; sonuçlanana kadar değişiklik yapılamaz.
					</div>
				{/if}

				{#if dropSuccess}
					<div
						class="mx-5 mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
					>
						{dropSuccess}
					</div>
				{/if}
				{#if dropError}
					<div
						class="mx-5 mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
					>
						{dropError}
					</div>
				{/if}

				<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
					Tabloyu yatay kaydırarak tüm sütunları görebilirsiniz.
				</p>
				{#if !addDropTableRows.length}
					<p class="px-5 py-8 text-center text-sm text-slate-400">Henüz satır yok.</p>
				{:else}
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<table class="min-w-[860px] w-full text-sm">
							<thead
								class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								<tr>
									<th class="w-8 shrink-0 px-2 py-3 sm:px-4"></th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Kod</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Tür</th>
									<th class="min-w-[11rem] px-4 py-3 text-left">Ders Adı</th>
									<th class="min-w-[7rem] px-4 py-3 text-left">Durum</th>
									<th class="whitespace-nowrap px-4 py-3 text-center">AKTS</th>
									<th class="min-w-[8rem] px-4 py-3 text-left">Öğr. Elemanı</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Gün/Saat</th>
									<th class="whitespace-nowrap px-4 py-3 text-right"></th>
								</tr>
							</thead>
							<tbody>
								{#each addDropTableRows as e}
									{@const eId = e.id ?? e.course_code}
									{@const marked = markedDrop.has(eId)}
									{@const st = e.status}
									<tr
										class="border-t border-black/5 dark:border-white/10 transition-colors {st ===
										'pending_drop'
											? 'bg-amber-50/50 dark:bg-amber-950/20'
											: st === 'draft'
												? 'bg-sky-50/40 dark:bg-sky-950/20'
												: marked
													? 'bg-red-50/60 dark:bg-red-950/20'
													: 'hover:bg-slate-50/50 dark:hover:bg-white/5'}"
									>
										<td class="px-4 py-3">
											{#if st === 'active' && !hasPendingAddDrop}
												<input
													type="checkbox"
													checked={marked}
													on:change={() => toggleDrop(eId)}
													class="accent-red-500 h-4 w-4 cursor-pointer"
												/>
											{:else if st === 'active' && hasPendingAddDrop}
												<span class="text-slate-300">—</span>
											{:else}
												<span class="text-slate-300">—</span>
											{/if}
										</td>
										<td
											class="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold {marked
												? 'text-red-500'
												: 'text-slate-500'}"
										>
											{e.course_code}
										</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs font-medium text-slate-600 dark:text-slate-400">{curriculumKindColumnLabel(e)}</td>
										<td
											class="min-w-[11rem] max-w-[22rem] px-4 py-3 font-medium leading-snug break-words {marked || st === 'pending_drop'
												? 'text-slate-500 line-through'
												: ''}"
										>
											{e.course_name}
										</td>
										<td class="px-4 py-3">
											<div class="flex flex-col gap-1">
												{#if st === 'draft'}
													<span
														class="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800 dark:bg-sky-900/50 dark:text-sky-200"
														>Taslak (eklenecek)</span
													>
												{:else if st === 'pending'}
													<span
														class="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-bold text-violet-800 dark:bg-violet-900/50 dark:text-violet-200"
														>Onayda (yeni ders)</span
													>
												{:else if st === 'pending_drop'}
													<span
														class="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800 dark:bg-amber-900/50 dark:text-amber-200"
														>Bırakma onayında</span
													>
												{:else}
													<span class="text-xs text-slate-400">Kayıtlı</span>
												{/if}
											</div>
										</td>
										<td class="whitespace-nowrap px-4 py-3 text-center">{e.akts}</td>
										<td class="min-w-[8rem] px-4 py-3 text-xs leading-snug break-words text-slate-500">{e.instructor_name ?? '—'}</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs">
											{e.day_of_week ?? '—'} {e.start_time ?? ''}
										</td>
										<td class="whitespace-nowrap px-4 py-3 text-right">
											{#if st === 'draft' && !hasPendingAddDrop}
												<button
													type="button"
													class="text-xs font-semibold text-red-600 hover:underline"
													on:click={() => removeDraftEnrollmentRow(eId)}>Eklemeyi iptal et</button>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
				{#if markedDrop.size > 0 || addDropDraftRows.length > 0}
					<div
						class="border-t border-black/5 bg-slate-50/50 px-5 py-3 text-xs text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-400"
					>
						Aktif derslerinizden çıkarmak istediklerinizi işaretleyin; açılan şubelerden yeni ders
						ekleyin. Tek talep olarak danışman onayına gönderilir; onay sonrası eklenenler kayda,
						işaretlenenler düşer.
					</div>
				{/if}
			</div>

			<div
				class="mt-6 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="flex flex-wrap items-start justify-between gap-2 border-b border-black/5 px-4 py-3 dark:border-white/10 sm:items-center sm:px-5"
				>
					<div class="min-w-0 text-sm font-bold text-slate-600 dark:text-slate-300">
						Ders ekle-bırak için açılan şubeler
					</div>
					<div class="flex flex-wrap items-center gap-3">
						<label class="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-2">
							<span class="shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400"
								>Sınıf ve yarıyıl</span
							>
							<select
								bind:value={catalogSectionFilterKey}
								class="max-w-[16rem] rounded-lg border border-black/10 bg-white px-2 py-1.5 text-xs font-medium text-slate-800 shadow-sm dark:border-white/10 dark:bg-white/10 dark:text-slate-100"
							>
								{#each catalogSlotFilterOptions as opt (opt.key)}
									<option value={opt.key}>{opt.label}</option>
								{/each}
							</select>
						</label>
						<div class="shrink-0 text-xs text-slate-500 dark:text-slate-400">
							<span
								>{catalogSectionsCountSummary(
									filteredAvailableCourses.length,
									availableCourses.length,
									addDropOfferPlaceholderRowsMeta > 0
										? {
												realSections: addDropRealSectionRowCount ?? 0,
												placeholders: addDropOfferPlaceholderRowsMeta
											}
										: undefined
								)}</span
							>
						</div>
					</div>
				</div>
				<p
					class="border-b border-black/5 bg-slate-50/90 px-4 py-2 text-[11px] leading-snug text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:px-5"
				>
					Derslerinizi sınıf ve yarıyılınıza göre listeleyebilirsiniz. Bölümünüzdeki tüm açılan şubeleri
					görmek için listeden <strong>Tümü — tüm sınıflar ve yarıyıllar</strong> seçeneğini kullanın.
					Şubesi tanımlı dersler ekle-bırak için seçilebilir; şubesiz satırlar yalnızca müfredat planı
					bilgisini gösterir.
				</p>
				{#if addDropSectionsEmptyHint}
					<p
						class="border-b border-black/5 bg-amber-50/90 px-4 py-2 text-left text-[11px] leading-snug text-amber-950 dark:border-amber-500/35 dark:bg-amber-950/35 dark:text-amber-50 sm:px-5"
					>
						{addDropSectionsEmptyHint}
					</p>
				{/if}
				<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
					Tabloyu yatay kaydırarak tüm sütunları görebilirsiniz.
				</p>
				{#if !filteredAvailableCourses.length}
					<div
						class="space-y-3 px-5 py-6 text-center text-sm leading-relaxed text-slate-500 dark:text-slate-400"
					>
						{#if availableCourses.length && catalogFilterActive}
							<p>
								Seçtiğiniz <strong>{catalogSlotLabelFromKey(catalogSectionFilterKey)}</strong> için
								açılmış şube bulunmuyor.
							</p>
							<button
								type="button"
								class="text-xs font-semibold text-sky-600 underline hover:text-sky-700 dark:text-sky-400"
								on:click={() => (catalogSectionFilterKey = 'all')}
								>Tüm açılan şubeleri listele ({availableCourses.length})</button
							>
						{:else}
							<p>Açılan ders bulunamadı.</p>
							{#if addDropCoursesPendingSections.length > 0}
								<div class="text-left text-xs text-slate-600 dark:text-slate-300">
									<p class="font-semibold text-slate-700 dark:text-slate-200">
										Müfredatta eksik; bu süre sorgusunda şube çıkmayan zorunlular
									</p>
									<ul
										class="mt-2 max-h-48 list-disc space-y-1 overflow-y-auto pl-5 marker:text-slate-400"
									>
										{#each addDropCoursesPendingSections as p}
											<li>
												<span class="font-mono font-semibold text-slate-500 dark:text-slate-400"
													>{p.course_code ?? '?'}</span
												>
												{#if p.course_name}
													<span class="text-slate-500 dark:text-slate-400">
														— {p.course_name}</span>
												{/if}
											</li>
										{/each}
									</ul>
								</div>
							{/if}
						{/if}
					</div>
				{:else}
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<table class="min-w-[1040px] w-full text-sm">
							<thead
								class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								<tr>
									<th class="whitespace-nowrap px-4 py-3 text-left">Kod</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Tür</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Sınıf</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Yarıyıl</th>
									<th class="min-w-[11rem] px-4 py-3 text-left">Ders Adı</th>
									<th class="whitespace-nowrap px-4 py-3 text-center">AKTS</th>
									<th class="min-w-[8rem] px-4 py-3 text-left">Öğr. Elemanı</th>
									<th class="whitespace-nowrap px-4 py-3 text-left">Gün/Saat</th>
									<th class="whitespace-nowrap px-4 py-3 text-center">Kontenjan</th>
									<th class="whitespace-nowrap px-4 py-3 text-center"></th>
								</tr>
							</thead>
							<tbody>
								{#each filteredAvailableCourses as c}
									{@const oph = !!(c as AvailableCourse & { offer_placeholder?: boolean }).offer_placeholder}
									{@const inCart =
										!oph &&
										enrollments.some(
											(x) =>
												x.status === 'draft' &&
												x.section_id === c.id &&
												(x.enrollment_reason || '') === 'add_drop'
										)}
									{@const full = !oph && c.enrolled >= c.capacity}
									<tr
										class="border-t border-black/5 dark:border-white/10 {oph
											? 'bg-amber-50/35 dark:bg-amber-950/15'
											: ''} {inCart
											? 'bg-sky-50/50 dark:bg-sky-900/10'
											: 'hover:bg-slate-50/50 dark:hover:bg-white/5'} transition-colors"
									>
										<td class="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold text-slate-500"
											>{c.course_code}</td
										>
										<td class="whitespace-nowrap px-4 py-3 text-xs font-medium text-slate-600 dark:text-slate-400">{curriculumKindColumnLabel(c)}</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{c.catalog_class_label ?? '—'}</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{c.catalog_half_label ?? '—'}</td>
										<td class="min-w-[12rem] max-w-[22rem] px-4 py-3 text-sm font-semibold leading-snug break-words text-slate-900 dark:text-slate-50">
											{c.course_name}
										</td>
										<td class="whitespace-nowrap px-4 py-3 text-center font-semibold">{c.akts}</td>
										<td class="min-w-[8rem] px-4 py-3 text-xs leading-snug break-words text-slate-500">{oph ? '—' : c.instructor_name}</td>
										<td class="whitespace-nowrap px-4 py-3 text-xs">{oph ? '—' : `${c.day_of_week ?? ''} ${c.start_time ?? ''}–${c.end_time ?? ''}`.trim() || '—'}</td>
										<td
											class="px-4 py-3 text-center text-xs {full ? 'text-red-500' : 'text-slate-500'}"
										>
											{c.enrolled}/{c.capacity}
											{#if full}<span
													class="ml-1 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-900/40 dark:text-red-300"
													>Dolu</span
												>{/if}
										</td>
										<td class="whitespace-nowrap px-4 py-3 text-center align-middle">
											{#if !String(c.id || '').trim()}
												<button
													type="button"
													on:click={() => toggleAddDropCart(c)}
													class="inline-flex shrink-0 items-center justify-center rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20 whitespace-nowrap"
													title="Şube seçilebilmesi için şube kaydı gerekir; yine de denediğinizde sistem uyarısı alırsınız."
												>
													Ders ekle
												</button>
											{:else if oph}
												<button
													type="button"
													on:click={() => toggleAddDropCart(c)}
													class="inline-flex shrink-0 items-center justify-center rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20 whitespace-nowrap"
													title="OBS’te bu kod için seçtiğiniz dönemde henüz şube satırı yok; yönetici şube açınca bu buton doğrudan taslak ekleyebilir."
												>
													Ders ekle
												</button>
											{:else if full && !inCart}
												<span class="text-xs text-slate-300">—</span>
											{:else if hasPendingAddDrop}
												<span class="text-xs text-slate-400" title="Talep kilitli">Kilitli</span>
											{:else}
												<button
													type="button"
													on:click={() => toggleAddDropCart(c)}
													class="inline-flex shrink-0 items-center justify-center rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors whitespace-nowrap
													{inCart
														? 'bg-sky-100 text-sky-700 ring-1 ring-sky-300 dark:bg-sky-900/40 dark:text-sky-300'
														: 'bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20'}"
												>
													{inCart ? 'Taslakta' : 'Ders ekle'}
												</button>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<!-- ================================================================ -->
			<!-- SINAV TAKVİMİ                                                     -->
			<!-- ================================================================ -->
		{:else if apiKey === 'exams'}
			<div
				class="-mx-1 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5 sm:mx-0"
			>
				<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
					Tabloyu yatay kaydırarak tüm sütunları görebilirsiniz.
				</p>
				<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
					<table class="min-w-[720px] w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="min-w-[11rem] px-4 py-3 text-left">Ders</th>
								<th class="whitespace-nowrap px-4 py-3 text-left">Tür</th>
								<th class="whitespace-nowrap px-4 py-3 text-left">Tarih</th>
								<th class="whitespace-nowrap px-4 py-3 text-left">Saat</th>
								<th class="whitespace-nowrap px-4 py-3 text-left">Derslik</th>
								<th class="whitespace-nowrap px-4 py-3 text-center">Ağırlık</th>
							</tr>
						</thead>
						<tbody>
							{#each exams as ex}
								<tr
									class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 transition-colors"
								>
									<td class="min-w-[11rem] max-w-[22rem] px-4 py-3">
										<div class="font-mono text-xs font-semibold text-slate-600 dark:text-slate-300">
											{ex.course_code}
										</div>
										<div class="mt-0.5 text-xs leading-snug break-words text-slate-700 dark:text-slate-200">
											{ex.course_name || '—'}
										</div>
									</td>
									<td class="whitespace-nowrap px-4 py-3">
										<span
											class="rounded-full px-2 py-0.5 text-xs font-medium
											{ex.exam_type === 'midterm'
												? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300'
												: ex.exam_type === 'final'
													? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
													: ex.exam_type === 'makeup'
														? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'
														: 'bg-slate-100 text-slate-600'}"
										>
											{ex.exam_type === 'midterm'
												? 'Vize'
												: ex.exam_type === 'final'
													? 'Final'
													: ex.exam_type === 'makeup'
														? 'Bütünleme'
														: ex.exam_type}
										</span>
									</td>
									<td class="whitespace-nowrap px-4 py-3 font-medium">{ex.exam_date}</td>
									<td class="whitespace-nowrap px-4 py-3 text-slate-500">{ex.exam_time}</td>
									<td class="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{ex.classroom}</td>
									<td class="whitespace-nowrap px-4 py-3 text-center font-semibold"
										>%{ex.weight_percent ?? 0}</td
									>
								</tr>
							{:else}
								<tr
									><td colspan="6" class="px-4 py-8 text-center text-sm text-slate-400"
										>Sınav bulunamadı.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- DERS PROGRAMI                                                     -->
			<!-- ================================================================ -->
		{:else if apiKey === 'schedule'}
			{@const DAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma']}
			<div class="space-y-4">
				<div class="flex flex-wrap items-end justify-between gap-3">
					<label class="block min-w-0 flex-1 sm:min-w-[200px]">
						<span class="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
							Akademik dönem
						</span>
						<select
							value={selectedScheduleTermId}
							on:change={(e) => {
								const v = e.currentTarget.value;
								selectedScheduleTermId = v;
								void reloadScheduleForTerm(v);
							}}
							disabled={!terms.length}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm font-medium outline-none dark:border-white/10 dark:bg-white/5 dark:text-slate-100 disabled:opacity-50"
						>
							{#each terms as t}
								<option value={t.id}
									>{(t.name && String(t.name).trim()) ||
										[t.academic_year, t.season].filter(Boolean).join(' ') ||
										t.id}</option
								>
							{/each}
						</select>
					</label>
				</div>
				<div class="space-y-3">
				{#each DAYS as day}
					{@const rows = schedule.filter((s) => s.day === day)}
					{#if rows.length}
						<div
							class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
						>
							<div
								class="bg-slate-100/70 px-4 py-2 text-xs font-bold text-slate-500 sm:px-5 dark:bg-white/5 dark:text-slate-400"
							>
								{day}
							</div>
							{#each rows as s}
								<div
									class="border-t border-black/5 px-4 py-3 dark:border-white/10 sm:px-5"
								>
									<div
										class="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4"
									>
										<div class="flex shrink-0 flex-wrap items-center gap-2 sm:gap-3">
											<span
												class="w-[6.75rem] shrink-0 font-mono text-xs tabular-nums text-slate-400"
												>{s.start}–{s.end}</span
											>
											<span
												class="shrink-0 rounded-lg bg-sky-100 px-2 py-0.5 font-mono text-xs font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
												>{s.course_code}</span
											>
										</div>
										<p
											class="min-w-0 flex-1 text-sm font-medium leading-snug text-slate-800 dark:text-slate-100"
										>
											{s.course_name}
										</p>
										<span
											class="shrink-0 text-xs text-slate-500 dark:text-slate-400 sm:text-right"
											>{s.classroom ?? '—'}</span
										>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{/each}
				{#if !schedule.length}
					<div
						class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400"
					>
						Bu dönem için programda görünecek kayıtlı ders bulunamadı.
					</div>
				{/if}
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- NOT LİSTESİ                                                       -->
			<!-- ================================================================ -->
		{:else if apiKey === 'grades'}
			<div class="space-y-4">
				<div class="flex flex-wrap items-end justify-between gap-3">
					<label class="block min-w-0 flex-1 sm:min-w-[200px]">
						<span class="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
							Akademik dönem
						</span>
						<select
							value={selectedGradesTermId}
							on:change={(e) => {
								const v = e.currentTarget.value;
								selectedGradesTermId = v;
								void reloadGradesForTerm(v);
							}}
							disabled={!terms.length}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm font-medium outline-none dark:border-white/10 dark:bg-white/5 dark:text-slate-100 disabled:opacity-50"
						>
							{#each terms as t}
								<option value={t.id}
									>{(t.name && String(t.name).trim()) ||
										[t.academic_year, t.season].filter(Boolean).join(' ') ||
										t.id}</option
								>
							{/each}
						</select>
					</label>
				</div>
				<p class="text-[11px] leading-snug text-slate-500 dark:text-slate-400">
					<strong>Ort.</strong> sütunu, her dersin <strong>kayıtlı olduğun şubesinde akademisyence girilmiş</strong>
					vize / final sınav yüzdeleriyle 100 üzerinden hesaplanır (büt notu girilmişse final payında kullanılır).
					Yüzdeler OBS’te hâlen tanımlı değilse gösterge <strong>%{LISTED_GRADE_VIZE_PCT}/{LISTED_GRADE_FINAL_PCT}</strong>
					varsayımına düşebilir — detay için satırdaki formül çizgisine bakın.
				</p>

			{#if gradesGrouped.length}
				<div class="space-y-8">
					{#each gradesGrouped as grp}
						<div>
							{#if gradesGrouped.length > 1}
								<div
									class="mb-3 flex items-center gap-3 border-b border-black/10 pb-2 dark:border-white/10"
								>
									<h2 class="text-sm font-black uppercase tracking-wide text-slate-800 dark:text-slate-100">
										{grp.label}
									</h2>
									<span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-white/10 dark:text-slate-400">
										Dönem
									</span>
								</div>
							{/if}
							<div
								class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
							>
							<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
								Tabloyu yatay kaydırarak tüm not sütunlarını görebilirsiniz.
							</p>
							<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
									<table class="min-w-[720px] w-full text-sm">
										<thead
											class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
										>
											<tr>
												<th class="min-w-[11rem] px-4 py-3 text-left">Ders</th>
												<th class="whitespace-nowrap px-4 py-3 text-center">Vize</th>
												<th class="whitespace-nowrap px-4 py-3 text-center">Final</th>
												<th class="whitespace-nowrap px-4 py-3 text-center">Büt</th>
												<th class="whitespace-nowrap px-4 py-3 text-center">Harf</th>
												<th
													class="whitespace-nowrap px-4 py-3 text-center"
													title="Şubede tanımlı vize/final yüzdeleriyle 100 üzerinden (hocanın girdiği paylar)."
												>
													Ort.<span class="text-[10px] font-normal opacity-70">100</span>
												</th>
												<th class="whitespace-nowrap px-4 py-3 text-center">Durum</th>
											</tr>
										</thead>
										<tbody>
											{#each grp.rows as g}
												{@const wg = listedGradeWeighted100(g)}
												<tr
													class="border-t border-black/5 hover:bg-slate-50/50 dark:border-white/10 transition-colors"
												>
													<td class="min-w-[11rem] max-w-[22rem] px-4 py-3">
														<div class="font-mono text-xs font-semibold text-slate-600 dark:text-slate-300">
															{g.course_code}
														</div>
														<div class="mt-0.5 text-xs leading-snug break-words text-slate-400">{g.course_name}</div>
													</td>
													<td class="whitespace-nowrap px-4 py-3 text-center font-medium">{g.midterm ?? '—'}</td>
													<td class="whitespace-nowrap px-4 py-3 text-center font-medium">{g.final ?? '—'}</td>
													<td class="whitespace-nowrap px-4 py-3 text-center font-medium text-amber-600 dark:text-amber-400">
														{g.makeup ?? '—'}
													</td>
													<td class="whitespace-nowrap px-4 py-3 text-center">
														{#if (g.is_published || g.is_finalized) && (g.letter_grade ?? '').toString().trim()}
															<span
																class="rounded-full px-2.5 py-0.5 text-xs font-bold {GRADE_COLOR[
																	String(g.letter_grade).trim()
																] ?? 'bg-slate-100 text-slate-600'}">{String(g.letter_grade).trim()}</span
															>
														{:else}<span class="text-slate-300">—</span>{/if}
													</td>
													<td class="whitespace-nowrap px-4 py-3 text-center align-middle">
														{#if wg}
															<details
																class="mx-auto max-w-[5.75rem] text-center [&>summary::-webkit-details-marker]:hidden [&>summary]:list-none"
															>
																<summary class="cursor-pointer select-none pb-px">
																	<span
																		class="text-sm font-bold tabular-nums text-slate-800 dark:text-slate-100"
																		>{wg.total.toFixed(2)}</span
																	>
																	<span
																		class="-mt-px block text-[9px] font-medium leading-none text-slate-400 dark:text-slate-500"
																		>⋯</span
																	>
																</summary>
																<div
																	class="mt-1 border-t border-black/10 pt-1 text-[10px] leading-tight text-slate-600 dark:border-white/10 dark:text-slate-400"
																>
																	<div class="font-mono tabular-nums opacity-95">
																		<span class="text-[9px] text-slate-500 dark:text-slate-400">{wg.vw}%·{wg.wf}%</span><br />
																		({wg.vw}×{wg.vNum}+{wg.wf}×{wg.fNum})÷100={wg.total.toFixed(2)}
																	</div>
																	{#if wg.usesMakeup}
																		<div class="mt-0.5 text-[9px] text-amber-800 dark:text-amber-400">
																			Final için büt
																		</div>
																	{/if}
																</div>
															</details>
														{:else}
															<span
																class="text-slate-300"
																title="Vize ile final veya büt birlikte girilince hesaplanır">—</span
															>
														{/if}
													</td>
													<td class="whitespace-nowrap px-4 py-3 text-center text-xs">
														{#if g.is_published}<span class="text-emerald-600 dark:text-emerald-400"
																>Yayınlandı</span
															>
														{:else if g.is_finalized}<span class="text-amber-600 dark:text-amber-400"
																>Kesinleşti</span
															>
														{:else}<span class="text-slate-400">Bekleniyor</span>{/if}
													</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<div
					class="overflow-hidden rounded-xl border border-black/10 bg-white p-12 text-center text-sm text-slate-400 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					Not bulunamadı.
				</div>
			{/if}
			</div>

			<!-- ================================================================ -->
			<!-- NOT HESAPLAMA                                                     -->
			<!-- ================================================================ -->
		{:else if apiKey === 'not-hesaplama'}
			<div class="space-y-6">
				<!-- Özet Kartları -->
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
					<div
						class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
					>
						<div class="text-[10px] font-bold uppercase tracking-wider text-slate-400">
							Dönem Ortalaması (ANO)
						</div>
						<div class="mt-2 text-3xl font-black text-sky-600 dark:text-sky-400">
							{mockAno.toFixed(2)}
						</div>
						<div class="mt-1 text-[10px] text-slate-400">Hesaplanan Tahmini Değer</div>
					</div>
					<div
						class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
					>
						<div class="text-[10px] font-bold uppercase tracking-wider text-slate-400">
							Hedef Genel Ortalama (AGNO)
						</div>
						<div class="mt-2 text-3xl font-black text-emerald-600 dark:text-emerald-400">
							{projectedAgno.toFixed(2)}
						</div>
						<div class="mt-1 text-[10px] text-slate-400">Mevcut: {cumulativeGpa?.toFixed(2) ?? '0.00'}</div>
					</div>
					<div class="flex flex-col gap-2">
						<button
							on:click={initMockFromEnrollments}
							class="flex h-full items-center justify-center rounded-xl border border-black/10 bg-slate-50 text-xs font-bold text-slate-600 hover:bg-slate-100 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
						>
							Aktif Derslerimi Getir
						</button>
						<button
							on:click={addMockCourse}
							class="flex h-full items-center justify-center rounded-xl bg-slate-800 text-xs font-bold text-white hover:bg-slate-700 dark:bg-sky-600 dark:hover:bg-sky-500"
						>
							Yeni Ders Ekle
						</button>
					</div>
				</div>

				<!-- Hesaplama Tablosu -->
				<div
					class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
						Geniş hesaplama tablosunu görmek için yatay kaydırın.
					</p>
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<table class="min-w-[800px] w-full text-sm">
							<thead
								class="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								<tr>
									<th class="px-4 py-3 text-left">Ders Kodu / Adı</th>
									<th class="px-4 py-3 text-center">AKTS</th>
									<th class="px-4 py-3 text-center">Vize (%/Not)</th>
									<th class="px-4 py-3 text-center">Final (%/Not)</th>
									<th class="px-4 py-3 text-center">Büt (Not)</th>
									<th class="px-4 py-3 text-center min-w-[7.5rem]" title="100 üzerinden ağırlıklı ara not"
										>Ortalama<br /><span class="font-normal opacity-75">(100)</span></th
									>
									<th class="px-4 py-3 text-center">Harf</th>
									<th class="px-4 py-3 text-right">İşlem</th>
								</tr>
							</thead>
							<tbody>
								{#each mockCourses as c, i}
									{@const br = getMockCourseBreakdown(c)}
									<tr class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 transition-all duration-200">
										<td class="px-4 py-3">
											<div class="flex flex-col">
												<input
													type="text"
													bind:value={c.code}
													class="w-20 border-none bg-transparent p-0 font-mono text-xs font-bold text-sky-600 focus:ring-0 dark:text-sky-400"
												/>
												<input
													type="text"
													bind:value={c.name}
													class="mt-0.5 border-none bg-transparent p-0 text-sm font-semibold text-slate-700 focus:ring-0 dark:text-slate-200"
												/>
											</div>
										</td>
										<td class="px-4 py-3 text-center">
											<input
												type="number"
												bind:value={c.akts}
												on:input={updateMockCalculations}
												class="w-12 border-none bg-transparent p-0 text-center text-sm font-bold text-slate-600 focus:ring-0 dark:text-slate-300"
											/>
										</td>
										<td class="px-4 py-3 text-center">
											<div class="flex items-center justify-center gap-1.5">
												<div class="flex items-center rounded-md bg-slate-100/50 px-1.5 py-1 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10">
													<input
														type="number"
														bind:value={c.vizeWeight}
														on:input={updateMockCalculations}
														class="w-7 border-none bg-transparent p-0 text-right text-[10px] font-bold text-slate-400 focus:ring-0"
													/>
													<span class="text-[10px] font-bold text-slate-300">%</span>
												</div>
												<input
													type="number"
													bind:value={c.vize}
													on:input={updateMockCalculations}
													placeholder="0"
													class="w-12 rounded-lg border-2 border-slate-200 bg-white px-1.5 py-1 text-center text-sm font-black text-slate-800 shadow-sm transition-all focus:border-sky-500 focus:ring-0 dark:border-white/10 dark:bg-slate-800 dark:text-white dark:focus:border-sky-400"
												/>
											</div>
										</td>
										<td class="px-4 py-3 text-center">
											<div class="flex items-center justify-center gap-1.5">
												<div class="flex items-center rounded-md bg-slate-100/50 px-1.5 py-1 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/10">
													<input
														type="number"
														bind:value={c.finalWeight}
														on:input={updateMockCalculations}
														class="w-7 border-none bg-transparent p-0 text-right text-[10px] font-bold text-slate-400 focus:ring-0"
													/>
													<span class="text-[10px] font-bold text-slate-300">%</span>
												</div>
												<input
													type="number"
													bind:value={c.final}
													on:input={updateMockCalculations}
													placeholder="0"
													class="w-12 rounded-lg border-2 border-slate-200 bg-white px-1.5 py-1 text-center text-sm font-black text-slate-800 shadow-sm transition-all focus:border-sky-500 focus:ring-0 dark:border-white/10 dark:bg-slate-800 dark:text-white dark:focus:border-sky-400"
												/>
											</div>
										</td>
										<td class="px-4 py-3 text-center">
											<div class="flex items-center justify-center">
												<input
													type="number"
													bind:value={c.makeup}
													on:input={updateMockCalculations}
													placeholder="—"
													class="w-12 rounded-lg border-2 border-amber-200 bg-amber-50/30 px-1.5 py-1 text-center text-sm font-black text-amber-900 shadow-sm transition-all focus:border-amber-500 focus:ring-0 dark:border-amber-900/40 dark:bg-amber-900/10 dark:text-amber-200 dark:focus:border-amber-400"
												/>
											</div>
										</td>
										<td class="px-4 py-3 text-center align-top">
											<div
												class="text-base font-black tabular-nums text-slate-800 dark:text-slate-100"
											>
												{br.total.toFixed(2)}
											</div>
											<div
												class="mx-auto mt-1 max-w-[11rem] text-center text-[9px] leading-snug text-slate-400 dark:text-slate-500 font-mono"
											>
												({c.vizeWeight}%×{br.vNum})+({c.finalWeight}%×{br.fEff})<br />
												={br.vizePart.toFixed(2)}+{br.finalPart.toFixed(2)}=<span
													class="font-bold text-slate-500 dark:text-slate-400">{br.total.toFixed(2)}</span
												>
											</div>
											{#if br.usesMakeup}
												<div class="mt-1 text-[9px] text-amber-700/90 dark:text-amber-400/90">
													Final yüzdesi ({c.finalWeight}%) için büt notu kullanıldı.
												</div>
											{/if}
										</td>
										<td class="px-4 py-3 text-center">
											<span
												class="inline-block min-w-[2.5rem] rounded-full px-2 py-0.5 text-xs font-black {GRADE_COLOR[
													c.harf
												] ?? 'bg-slate-100 text-slate-600'}"
											>
												{c.harf}
											</span>
										</td>
										<td class="px-4 py-3 text-right">
											<button
												on:click={() => removeMockCourse(i)}
												class="text-slate-300 hover:text-red-500 transition-colors"
												title="Dersi Sil"
											>
												<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
												</svg>
											</button>
										</td>
									</tr>
								{:else}
									<tr>
										<td colspan="8" class="px-4 py-12 text-center">
											<div class="text-slate-400 text-sm">Hesaplanacak ders bulunamadı.</div>
											<button
												on:click={initMockFromEnrollments}
												class="mt-3 text-xs font-bold text-sky-600 hover:underline"
											>
												Aktif Derslerimi Getir
											</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>

				<!-- Bilgi Notu -->
				<div class="rounded-xl bg-amber-50/50 p-4 dark:bg-amber-950/10 border border-amber-100 dark:border-amber-900/30">
					<div class="flex gap-3">
						<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-amber-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
						</svg>
						<div class="text-xs text-amber-800 dark:text-amber-200 leading-normal space-y-2">
							<p class="font-bold">Not Hesaplama Hakkında Bilgilendirme</p>
							<p class="opacity-95">
								<strong>Ders notu (100 üzerinden):</strong> Yüzdeler o dersteki sınav payını gösterir. Ortalama =
								<span class="font-mono text-[11px] whitespace-normal sm:whitespace-nowrap"
									>(Vize × Vize%) / 100 + (Final × Final%) / 100</span
								>. Büt yazılmışsa son terimde Final yerine <strong>büt</strong> notu, yine Final ağırlığı ile kullanılır.
								Aşağıda her satırda bu matematik üçümlü olarak (ör.&nbsp;26,00&nbsp;+&nbsp;30,00) gösterilir.
								<strong>ANO</strong> ise harfin 4'lük puana karşılığı ile AKTS ağırlıklı olarak hesaplanır.
							</p>
							<p class="opacity-90">
								Bu araç, Doğuş Üniversitesi Ön Lisans ve Lisans Eğitim-Öğretim ve Sınav Yönetmeliği (Madde 34 ve 35)
								baz alınarak hazırlanmıştır. Harf notu baremleri (A+, A, B+…) otomatik uygulanır. AGNO tahmini için
								transkript AKTS'i ve mevcut GNO kullanılır.
							</p>
						</div>
					</div>
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- DÖNEM ORTALAMALARI                                                -->
			<!-- ================================================================ -->
		{:else if apiKey === 'gpa'}
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
				<div
					class="flex flex-col items-center justify-center rounded-xl border border-black/10 bg-white p-8 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="text-xs font-bold tracking-wider text-slate-400">KÜMÜLATİF GNO</div>
					<div class="mt-3 text-5xl font-black text-sky-600 dark:text-sky-400">
						{cumulativeGpa?.toFixed(2) ?? '—'}
					</div>
					<div class="mt-2 text-xs text-slate-400">4.00 üzerinden</div>
				</div>
				<div
					class="col-span-2 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<div class="min-w-[22rem] sm:min-w-0">
							<div
								class="grid grid-cols-3 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								<div class="min-w-0">Dönem</div>
								<div class="text-center whitespace-nowrap">DNO</div>
								<div class="text-center whitespace-nowrap">AKTS</div>
							</div>
							{#each gpaTerms as { term_name: string; term_gpa: number | null; akts_completed: number }[] as t}
								<div
									class="grid grid-cols-3 border-t border-black/5 px-5 py-3.5 text-sm dark:border-white/10"
								>
									<div class="min-w-0 font-medium leading-snug break-words">{t.term_name}</div>
									<div
										class="text-center font-bold whitespace-nowrap {t.term_gpa && t.term_gpa >= 2.0
											? 'text-emerald-600 dark:text-emerald-400'
											: 'text-red-600 dark:text-red-400'}"
									>
										{t.term_gpa?.toFixed(2) ?? '—'}
									</div>
									<div class="text-center text-slate-500 whitespace-nowrap tabular-nums">{t.akts_completed}</div>
								</div>
							{/each}
						</div>
					</div>
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- TRANSKRİPT                                                        -->
			<!-- ================================================================ -->
		{:else if apiKey === 'transcript' && transcript}
			<!-- Resmi başlık -->
			<div
				class="mb-4 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5 print:shadow-none print:border-0"
			>
				<div
					class="border-b border-black/10 bg-slate-50 px-4 py-4 dark:border-white/10 dark:bg-white/5 print:bg-white sm:px-6"
				>
					<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
						<div class="min-w-0">
							<div class="text-xs font-bold uppercase tracking-widest text-slate-400">
								Doğuş Üniversitesi
							</div>
							<div class="mt-1 break-words text-lg font-bold text-slate-900 dark:text-slate-100">
								Akademik Transkript
							</div>
							<div class="mt-1 break-words text-sm text-slate-500">
								{profile?.full_name ?? $user?.name ?? '—'} · No: {profile?.student_no ?? '—'}
							</div>
							<div class="break-words text-xs text-slate-400">
								{profile?.department_name ?? '—'} · {profile?.program ?? 'Lisans'}
							</div>
						</div>
						<div class="flex shrink-0 flex-wrap items-center justify-between gap-4 border-t border-black/5 pt-4 sm:flex-nowrap sm:justify-end sm:border-t-0 sm:pt-0">
							<div class="text-center">
								<div class="text-xs font-semibold text-slate-400">Kümülatif GNO</div>
								<div
									class="mt-1 text-3xl font-black {(cumulativeGpa ?? 0) >= 3.0
										? 'text-emerald-600 dark:text-emerald-400'
										: (cumulativeGpa ?? 0) >= 2.0
											? 'text-sky-600 dark:text-sky-400'
											: 'text-red-500'}"
								>
									{cumulativeGpa?.toFixed(2) ?? '—'}
								</div>
							</div>
							<div class="text-center">
								<div class="text-xs font-semibold text-slate-400">Toplam AKTS</div>
								<div class="mt-1 text-3xl font-black text-slate-700 dark:text-slate-200">
									{transcriptTotalAkts ?? '—'}
								</div>
							</div>
							<button
								on:click={() => window.print()}
								type="button"
								class="flex items-center gap-1.5 rounded-lg border border-black/10 px-3 py-2 text-xs font-medium hover:bg-slate-100 dark:border-white/10 dark:hover:bg-white/10 print:hidden"
							>
								🖨 Yazdır / PDF
							</button>
						</div>
					</div>
				</div>
			</div>

			<!-- Dönemler -->
			{#each transcript as { term_name: string; term_gpa: number; term_akts: number; courses: { code: string; name: string; credits: number; akts: number; letter: string; grade_point: number }[] }[] as term}
				<div
					class="mb-3 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<!-- Dönem başlığı -->
					<div class="flex flex-col gap-2 bg-slate-100 px-4 py-3 dark:bg-white/10 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-5">
						<div class="min-w-0 font-semibold leading-snug break-words text-slate-700 dark:text-slate-200">{term.term_name}</div>
						<div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
							<span
								>Dönem AKTS: <strong class="text-slate-700 dark:text-slate-200"
									>{term.term_akts}</strong
								></span
							>
							<span
								>DNO: <strong
									class={term.term_gpa >= 3.0
										? 'text-emerald-600 dark:text-emerald-400'
										: term.term_gpa >= 2.0
											? 'text-sky-600 dark:text-sky-400'
											: 'text-red-500'}>{term.term_gpa.toFixed(2)}</strong
								></span
							>
						</div>
					</div>
					<!-- Ders satırları -->
					<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
						Tabloyu yatay kaydırarak tam transkripti görebilirsiniz.
					</p>
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<table class="min-w-[600px] w-full text-sm">
							<thead class="bg-slate-50/80 text-xs font-semibold text-slate-500 dark:bg-white/5">
								<tr>
									<th class="whitespace-nowrap px-5 py-2 text-left">Ders Kodu</th>
									<th class="min-w-[12rem] px-5 py-2 text-left">Ders Adı</th>
									<th class="whitespace-nowrap px-5 py-2 text-center">Kredi</th>
									<th class="whitespace-nowrap px-5 py-2 text-center">AKTS</th>
									<th class="whitespace-nowrap px-5 py-2 text-center">Not Puanı</th>
									<th class="whitespace-nowrap px-5 py-2 text-center">Harf Notu</th>
								</tr>
							</thead>
							<tbody>
								{#each term.courses as c}
									<tr class="border-t border-black/5 dark:border-white/10">
										<td class="whitespace-nowrap px-5 py-2.5 font-mono text-xs font-semibold text-slate-500"
											>{c.code}</td
										>
										<td class="max-w-[20rem] px-5 py-2.5 font-medium leading-snug break-words">{c.name}</td>
										<td class="whitespace-nowrap px-5 py-2.5 text-center text-xs text-slate-400">{c.credits}</td>
										<td class="whitespace-nowrap px-5 py-2.5 text-center text-xs text-slate-400">{c.akts}</td>
										<td class="whitespace-nowrap px-5 py-2.5 text-center text-xs text-slate-500"
											>{c.grade_point.toFixed(2)}</td
										>
										<td class="whitespace-nowrap px-5 py-2.5 text-center">
											<span
												class="rounded-full px-2.5 py-0.5 text-xs font-bold {GRADE_COLOR[
													c.letter
												] ?? 'bg-slate-100 text-slate-600'}">{c.letter}</span
											>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			{/each}

			<!-- ================================================================ -->
			<!-- MÜFREDAT DURUMU                                                   -->
			<!-- ================================================================ -->
		{:else if apiKey === 'curriculum'}
			{#if curriculum && (curriculum.categories?.length ?? 0) > 0}
				<div class="max-h-[calc(100vh-12rem)] overflow-y-auto pr-1 space-y-4">
					<!-- Genel ilerleme -->
					<div
						class="mb-4 overflow-hidden rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
					>
						<div class="flex flex-wrap items-start justify-between gap-4">
							<div class="min-w-0 flex-1">
								<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">Program</div>
								<div class="mt-1 break-words text-sm font-bold">{curriculum.program ?? '—'}</div>
							</div>
							<div class="text-right shrink-0">
								<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">
									Genel İlerleme
								</div>
								<div class="mt-1 text-2xl font-bold text-sky-600 dark:text-sky-400">
									%{(curriculum.overall_progress_pct ?? 0).toFixed(1)}
								</div>
							</div>
						</div>
						<div
							class="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-white/10"
						>
							<div
								class="h-full rounded-full bg-sky-500 transition-all"
								style="width:{curriculum.overall_progress_pct ?? 0}%"
							></div>
						</div>
						<p class="mt-3 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
							Kayıtlı derslerinizin tamamlanma özeti. Genel ilerleme, bu listede yer alan dersler
							içinde başarıyla tamamladıklarınızın oranına göre hesaplanır. Programınızda henüz
							alınmamış dersler bu ekranda ayrıca listelenmez.
						</p>
					</div>

					<!-- Kategoriler -->
					{#each curriculum.categories ?? [] as cat}
						{@const total = cat.courses.length}
						{@const done = cat.courses.filter((c) => c.status === 'tamamlandi').length}
						{@const ongoing = cat.courses.filter((c) => c.status === 'devam_ediyor').length}
						<div
							class="mb-4 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
						>
							<div class="flex flex-col gap-2 border-b border-black/10 bg-slate-50 px-4 py-3 dark:border-white/10 dark:bg-white/5 sm:flex-row sm:items-center sm:justify-between sm:gap-0 sm:px-5">
								<div class="min-w-0 text-sm font-semibold leading-snug break-words sm:text-base">{cat.name}</div>
								<div class="shrink-0 text-xs text-slate-500">
									{done}/{total} tamamlandı
									{#if ongoing > 0}<span
											class="ml-1.5 rounded-full bg-sky-100 px-1.5 py-0.5 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
											>{ongoing} devam</span
										>{/if}
								</div>
							</div>
							<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
								Satırları yatay kaydırarak tüm sütunları görebilirsiniz.
							</p>
							<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
								<div class="min-w-[620px]">
							{#each cat.courses as c}
								{@const statusColors = {
									tamamlandi:
										'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
									devam_ediyor: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',
									alinmadi: 'bg-slate-100 text-slate-500 dark:bg-white/5 dark:text-slate-400'
								}}
								{@const statusLabel = {
									tamamlandi: 'Tamamlandı',
									devam_ediyor: 'Devam Ediyor',
									alinmadi: 'Alınmadı'
								}}
								<div
									class="grid grid-cols-12 items-center border-t border-black/5 px-5 py-2.5 text-sm dark:border-white/10"
								>
									<div class="col-span-2 font-mono text-xs font-semibold text-slate-500">
										{c.code}
									</div>
									<div class="col-span-6 min-w-0 font-medium leading-snug break-words">{c.name}</div>
									<div class="col-span-1 text-center text-xs text-slate-400">{c.akts} AKTS</div>
									<div class="col-span-2 text-center">
										{#if c.grade}
											<span
												class="rounded-full px-2 py-0.5 text-xs font-bold {GRADE_COLOR[c.grade] ??
													'bg-slate-100 text-slate-600'}">{c.grade}</span
											>
										{:else}
											<span class="text-slate-300">—</span>
										{/if}
									</div>
									<div class="col-span-1 text-right">
										<span
											class="rounded-full px-2 py-0.5 text-[10px] font-semibold {statusColors[
												c.status as keyof typeof statusColors
											] ?? statusColors.alinmadi}"
										>
											{statusLabel[c.status as keyof typeof statusLabel] ?? c.status}
										</span>
									</div>
								</div>
							{/each}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<div
					class="rounded-xl border border-black/10 bg-white p-8 text-center text-sm text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400"
				>
					Müfredat listesi için veritabanında kayıtlı ders bulunamadı. Kayıtlı dersleriniz ve
					notlarınız eklendikçe burada gruplanır.
				</div>
			{/if}

			<!-- ================================================================ -->
			<!-- DEVAMSIZLIK                                                       -->
			<!-- ================================================================ -->
		{:else if apiKey === 'attendance'}
			<div class="space-y-4">
				<div class="flex flex-wrap items-end justify-between gap-3">
					<label class="block min-w-0 flex-1 sm:min-w-[200px]">
						<span class="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-400">
							Akademik dönem
						</span>
						<select
							value={selectedAttendanceTermId}
							on:change={(e) => {
								const v = e.currentTarget.value;
								selectedAttendanceTermId = v;
								void reloadAttendanceForTerm(v);
							}}
							disabled={!terms.length}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm font-medium outline-none dark:border-white/10 dark:bg-white/5 dark:text-slate-100 disabled:opacity-50"
						>
							{#each terms as t}
								<option value={t.id}
									>{(t.name && String(t.name).trim()) ||
										[t.academic_year, t.season].filter(Boolean).join(' ') ||
										t.id}</option
								>
							{/each}
						</select>
					</label>
					<details
						class="group relative shrink-0 rounded-lg border border-black/10 bg-white dark:border-white/10 dark:bg-white/5"
					>
						<summary
							class="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-600 outline-none marker:hidden dark:text-slate-300 [&::-webkit-details-marker]:hidden"
						>
							<span class="inline-flex items-center gap-1.5">
								<span
									class="inline-flex size-5 items-center justify-center rounded-full bg-slate-100 text-[11px] font-bold text-slate-600 dark:bg-white/10 dark:text-slate-200"
									>i</span
								>
								Devamsızlık hakkı
							</span>
						</summary>
						<div
							class="absolute right-0 z-30 mt-2 w-[min(100vw-1.25rem,18rem)] rounded-xl border border-black/10 bg-white p-3 text-[11px] leading-relaxed text-slate-600 shadow-lg dark:border-white/15 dark:bg-slate-900 dark:text-slate-300"
						>
							<p>
								Kayıtlı olduğunuz her ders için, o güne kadar işlenen hafta sayısının yaklaşık
								<strong>%30’una</strong> karşılık gelen devamsızlık hakkınız bulunur. Bu hakkın
								kullanımı tabloda <strong>Devamsız</strong> sütununda görüntülenir.
							</p>
						</div>
					</details>
				</div>

				<div
					class="-mx-1 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5 sm:mx-0"
				>
					<p class="border-b border-black/5 bg-slate-50/90 px-3 py-1.5 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400 sm:hidden">
						Tüm devamsızlık sütunlarını görmek için yatay kaydırın.
					</p>
					<div class="overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]">
						<table class="min-w-[480px] w-full text-sm">
							<thead
								class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								<tr>
									<th class="px-3 py-3 text-left sm:px-4">Ders</th>
									<th
										class="px-2 py-3 text-center sm:px-4"
										title="Yoklaması girilmiş son hafta (işlenen süre)"
										>Toplam</th
									>
									<th class="px-2 py-3 text-center sm:px-4" title="Devamsız oturum sayısı"
										>Devamsız</th
									>
									<th class="px-3 py-3 text-center sm:px-4">Devam %</th>
									<th class="px-2 py-3 text-center sm:px-4" title="Devam yüzdesine göre">Durum</th>
								</tr>
							</thead>
							<tbody>
								{#each attendance as a}
									{@const lim30 =
										typeof a.allowed_absences_30pct === 'number'
											? a.allowed_absences_30pct
											: floorPct30Quota(a.total_weeks)}
									{@const fazla =
										typeof a.absences_over_30pct === 'number'
											? a.absences_over_30pct
											: Math.max(0, a.absent_count - lim30)}
									{@const attUi = attendancePctBarClasses(a.attendance_pct, fazla)}
									{@const absCls = absentCellClass(a.attendance_pct, fazla)}
									<tr class="border-t border-black/5 dark:border-white/10">
										<td class="px-3 py-3 sm:px-4">
											<div class="font-mono text-xs font-semibold">{a.course_code}</div>
											<div class="text-xs text-slate-400">{a.course_name}</div>
										</td>
										<td class="px-2 py-3 text-center tabular-nums sm:px-4">{a.total_weeks}</td>
										<td
											class="px-2 py-3 text-center font-semibold tabular-nums {absCls}">{a.absent_count}</td
										>
										<td class="px-3 py-3 text-center sm:px-4">
											<div class="font-bold tabular-nums {attUi.pct}">
												%{a.attendance_pct.toFixed(1)}
											</div>
											<div
												class="mt-1 mx-auto h-1.5 w-14 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10"
											>
												<div
													class="h-full rounded-full transition-all {attUi.bar}"
													style="width:{a.attendance_pct}%"
												></div>
											</div>
										</td>
										<td class="px-2 py-3 text-center sm:px-4">
											<span
												class="rounded-full px-2 py-0.5 text-[10px] font-medium sm:text-xs sm:px-2.5
												{a.status === 'ok'
													? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
													: a.status === 'warning'
														? 'bg-sky-100 text-sky-900 dark:bg-sky-950/40 dark:text-sky-100'
														: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}"
											>
												{a.status === 'ok' ? 'İyi' : a.status === 'warning' ? 'Uyarı' : 'Kritik'}
											</span>
										</td>
									</tr>
								{:else}
									<tr
										><td colspan="5" class="px-4 py-8 text-center text-sm text-slate-400">Devamsızlık kaydı yok.</td
										></tr
									>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- DUYURULAR                                                         -->
			<!-- ================================================================ -->
		{:else if apiKey === 'announcements'}
			{#if announcements.length}
				<div class="space-y-3">
					{#each announcements as ann}
						<div
							class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
						>
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0 flex-1 font-semibold leading-snug break-words">{ann.title}</div>
								<span
									class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-white/10 dark:text-slate-300"
								>
									{ann.audience_type === 'all' ? 'Genel' : 'Bölüm'}
								</span>
							</div>
							<p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{ann.content}</p>
							<div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
								{#if ann.created_by_name}
									<span class="font-medium text-slate-500 dark:text-slate-400"
										>Gönderen: {ann.created_by_name}</span
									>
									<span class="hidden sm:inline">·</span>
								{/if}
								<span>{ann.published_at ?? ''}</span>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<div
					class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400"
				>
					Duyuru yok.
				</div>
			{/if}

			<!-- ================================================================ -->
			<!-- GELEN / GÖNDERİLEN MESAJLAR                                      -->
			<!-- ================================================================ -->
		{:else if apiKey === 'inbox' || apiKey === 'sent'}
			{@const msgs =
				apiKey === 'inbox'
					? inboxMsgs.filter((m) => m.status !== 'deleted')
					: sentMsgs.filter((m) => m.status !== 'deleted')}

			<!-- Başlık + Yeni Mesaj -->
			<div class="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
				<span class="min-w-0 text-xs text-slate-400">{msgs.length} mesaj</span>
				<button
					on:click={() => (showCompose = true)}
					type="button"
					class="flex w-full shrink-0 items-center justify-center gap-2 rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors sm:w-auto"
				>
					Yeni Mesaj
				</button>
			</div>

			<!-- Mesajlar -->
			<div class="space-y-2">
				{#each msgs as m}
					<div
						class="rounded-xl border bg-white p-5 shadow-sm dark:bg-white/5
						{apiKey === 'inbox' && !m.is_read
							? 'border-sky-200 dark:border-sky-800'
							: 'border-black/10 dark:border-white/10'}"
					>
						<div class="flex items-start justify-between gap-3">
							<div
								class="min-w-0 flex-1 font-semibold text-sm leading-snug break-words {apiKey === 'inbox' && !m.is_read
									? 'text-sky-700 dark:text-sky-300'
									: ''}"
							>
								{m.subject}
							</div>
							{#if apiKey === 'inbox' && !m.is_read}
								<span
									class="shrink-0 rounded-full bg-sky-100 px-1.5 py-0.5 text-[10px] font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
									>YENİ</span
								>
							{/if}
						</div>
						<div class="mt-1 text-xs text-slate-400">
							{apiKey === 'inbox'
								? (m.sender_name ?? m.sender_type)
								: `Alıcı: ${m.receiver_name ?? m.receiver_type}`} · {m.sent_at}
						</div>
						<p class="mt-2 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{m.body}</p>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400 dark:border-white/15"
					>
						{apiKey === 'inbox' ? 'Gelen kutunuz boş.' : 'Henüz mesaj göndermediniz.'}
					</div>
				{/each}
			</div>

			<!-- Compose modal -->
			{#if showCompose}
				<div
					class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 backdrop-blur-sm sm:p-4"
				>
					<div
						class="max-h-[min(90dvh,40rem)] w-full max-w-lg overflow-y-auto overscroll-contain rounded-2xl border border-black/10 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-slate-900 sm:p-6"
					>
						<div class="mb-5 flex items-center justify-between">
							<div class="font-bold text-slate-800 dark:text-slate-100">Yeni Mesaj</div>
							<button
								on:click={() => (showCompose = false)}
								type="button"
								class="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200">✕</button
							>
						</div>
						{#if composeError}
							<div
								class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
							>
								{composeError}
							</div>
						{/if}
						<div class="space-y-3">
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Alıcı</div>
								<input
									bind:value={composeForm.receiver_name}
									placeholder="Danışmanım"
									class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
								/>
							</label>
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Konu</div>
								<input
									bind:value={composeForm.subject}
									placeholder="Mesaj konusu"
									class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
								/>
							</label>
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Mesaj</div>
								<textarea
									bind:value={composeForm.body}
									rows="6"
									placeholder="Mesajınızı yazın…"
									class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800 resize-none"
								></textarea>
							</label>
							<div class="flex gap-2 pt-1">
								<button
									on:click={sendMessage}
									disabled={composeSending || !composeForm.subject || !composeForm.body}
									type="button"
									class="flex-1 rounded-xl bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
								>
									{composeSending ? 'Gönderiliyor…' : 'Gönder'}
								</button>
								<button
									on:click={() => (showCompose = false)}
									type="button"
									class="rounded-xl border border-black/10 px-4 py-2.5 text-sm hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5 transition-colors"
								>
									İptal
								</button>
							</div>
						</div>
					</div>
				</div>
			{/if}

			<!-- ================================================================ -->
			<!-- BELGE TALEBİ                                                      -->
			<!-- ================================================================ -->
		{:else if apiKey === 'doc-request'}
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-5 font-bold">Yeni Belge Talebi</div>
					{#if docSuccess}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							{docSuccess}
						</div>{/if}
					{#if docError}<div
							class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
						>
							{docError}
						</div>{/if}
					<div class="space-y-4">
						<label class="block">
							<div class="mb-1.5 text-xs font-semibold text-slate-500">Talep Eden Kurum</div>
							<input
								bind:value={docForm.requesting_institution}
								placeholder="Kurum adı"
								class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/20 dark:border-white/10 dark:bg-white/5"
							/>
						</label>
						<label class="block">
							<div class="mb-1.5 text-xs font-semibold text-slate-500">Talep Nedeni</div>
							<input
								bind:value={docForm.request_reason}
								placeholder="Neden gerekiyor?"
								class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/20 dark:border-white/10 dark:bg-white/5"
							/>
						</label>
						<label class="block">
							<div class="mb-1.5 text-xs font-semibold text-slate-500">Belge Türü</div>
							<select
								bind:value={docForm.document_type}
								class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none dark:border-white/10 dark:bg-white/5"
							>
								<option value="öğrenci_belgesi">Öğrenci Belgesi</option>
								<option value="transkript">Transkript</option>
								<option value="disiplin_belgesi">Disiplin Belgesi</option>
							</select>
						</label>
						<label class="block">
							<div class="mb-1.5 text-xs font-semibold text-slate-500">Belge Dili / Tipi</div>
							<select
								bind:value={docForm.document_subtype}
								class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none dark:border-white/10 dark:bg-white/5"
							>
								{#each docSubtypes as sub}<option value={sub}>{sub}</option>{/each}
							</select>
						</label>
						<button
							on:click={submitDocRequest}
							disabled={docSubmitting}
							type="button"
							class="w-full rounded-xl bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
						>
							{docSubmitting ? 'Gönderiliyor…' : 'Talep Gönder'}
						</button>
					</div>
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-bold">Geçmiş Talepler</div>
					{#if docRequests.length}
						<div class="space-y-2">
							{#each docRequests as req}
								<div class="rounded-xl border border-black/5 p-4 dark:border-white/10">
									<div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
										<span class="min-w-0 text-sm font-medium leading-snug break-words"
											>{req.document_type} — {req.document_subtype}</span
										>
										<span
											class="shrink-0 self-start rounded-full px-2 py-0.5 text-xs sm:self-center {req.status === 'tamamlandı'
												? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
												: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}"
										>
											{req.status}
										</span>
									</div>
									<div class="mt-1 text-xs text-slate-400">
										{req.requesting_institution} · {req.created_at?.slice(0, 10)}
									</div>
								</div>
							{/each}
						</div>
					{:else}
						<div class="text-sm text-slate-400">Henüz talep yok.</div>
					{/if}
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- ŞİFRE DEĞİŞTİR                                                   -->
			<!-- ================================================================ -->
		{:else if apiKey === 'change-pw'}
			<div
				class="mx-auto max-w-md rounded-xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="mb-1 font-bold">Şifre Değiştir</div>
				<p class="mb-5 text-xs text-slate-400">
					Kurallar: en az 8 karakter, 1 büyük harf, 1 rakam.
				</p>
				{#if pwOk}<div
						class="mb-4 rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
					>
						{pwOk}
					</div>{/if}
				{#if pwErr}<div
						class="mb-4 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
					>
						{pwErr}
					</div>{/if}
				<div class="space-y-4">
					{#each [['Mevcut Şifre', 'current_password'], ['Yeni Şifre', 'new_password'], ['Yeni Şifre (Tekrar)', 'confirm_password']] as [lbl, field]}
						<label class="block">
							<div class="mb-1.5 text-xs font-semibold text-slate-500">{lbl}</div>
							<input
								bind:value={pwForm[field as keyof typeof pwForm]}
								type="password"
								autocomplete="off"
								class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/20 dark:border-white/10 dark:bg-white/5"
							/>
						</label>
					{/each}
					<button
						on:click={changePassword}
						disabled={pwBusy}
						type="button"
						class="w-full rounded-xl bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
					>
						{pwBusy ? 'Güncelleniyor…' : 'Şifreyi Güncelle'}
					</button>
				</div>
			</div>
		{:else}
			<div
				class="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 p-8 text-center dark:border-white/10 dark:bg-white/5"
			>
				<div class="text-3xl">📋</div>
				<div class="mt-3 font-semibold text-slate-600 dark:text-slate-300">{pageTitle}</div>
				<p class="mt-1 text-sm text-slate-400">Bu sayfa yüklenemedi veya desteklenmiyor.</p>
			</div>
		{/if}
	</div>

	<!-- Floating compose button (mesajlar sayfasında değilken) -->
		{#if !['inbox', 'sent'].includes(apiKey) && !showCompose}
		<button
			on:click={() => (showCompose = true)}
			type="button"
			title="Mesaj Yaz"
			class="fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-[max(1.25rem,env(safe-area-inset-right))] z-40 flex h-11 w-11 items-center justify-center rounded-full bg-sky-500 text-sm font-bold leading-none text-white shadow-lg hover:bg-sky-400 transition-all hover:scale-105"
		>
			+
		</button>
	{/if}

	<!-- Compose modal (sayfa dışından açılınca) -->
	{#if showCompose && !['inbox', 'sent'].includes(apiKey)}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 backdrop-blur-sm sm:p-4">
			<div
				class="max-h-[min(90dvh,40rem)] w-full max-w-lg overflow-y-auto overscroll-contain rounded-2xl border border-black/10 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-slate-900 sm:p-6"
			>
				<div class="mb-5 flex items-center justify-between">
					<div class="font-bold text-slate-800 dark:text-slate-100">Yeni Mesaj</div>
					<button
						on:click={() => (showCompose = false)}
						type="button"
						class="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200">✕</button
					>
				</div>
				<div class="space-y-3">
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Alıcı</div>
						<input
							bind:value={composeForm.receiver_name}
							placeholder="Danışmanım"
							class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
						/>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Konu</div>
						<input
							bind:value={composeForm.subject}
							placeholder="Mesaj konusu"
							class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
						/>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Mesaj</div>
						<textarea
							bind:value={composeForm.body}
							rows="5"
							placeholder="Mesajınızı yazın…"
							class="w-full resize-none rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
						></textarea>
					</label>
					{#if composeSuccess}<div
							class="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							{composeSuccess}
						</div>{/if}
					{#if composeError}<div
							class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
						>
							{composeError}
						</div>{/if}
					<div class="flex gap-2 pt-1">
						<button
							on:click={sendMessage}
							disabled={composeSending || !composeForm.subject || !composeForm.body}
							type="button"
							class="flex-1 rounded-xl bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
						>
							{composeSending ? 'Gönderiliyor…' : 'Gönder'}
						</button>
						<button
							on:click={() => (showCompose = false)}
							type="button"
							class="rounded-xl border border-black/10 px-4 py-2.5 text-sm hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5 transition-colors"
						>
							İptal
						</button>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>
