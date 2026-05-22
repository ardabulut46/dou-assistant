<script lang="ts">
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import { tick } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import { updateUserPassword } from '$lib/apis/auths';
	import {
		getDouAcademicSections,
		getDouSectionStudents,
		getDouSectionGrades,
		putDouSectionGrades,
		deleteDouSectionGrade,
		finalizeDouSectionGrades,
		putDouSectionGradeWeights,
		getDouSectionExams,
		getDouAcademicClassrooms,
		createDouSectionExam,
		updateDouSectionExam,
		deleteDouSectionExam,
		putDouSectionAttendance,
		getDouSectionAttendance,
		getDouAcademicAdvisees,
		getDouAcademicApprovalRequests,
		resolveDouApprovalRequest,
		getDouAdviseeEnrollments,
		finalizeDouAdviseeSchedule,
		rejectDouAdviseeSchedule,
		getDouTerms,
		getDouInbox,
		getDouSent,
		sendDouMessageApi,
		markDouMessageRead,
		createDouAcademicAnnouncement,
		getDouAcademicAnnouncements,
		updateDouAcademicAnnouncement,
		deleteDouAcademicAnnouncement,
		type AcademicAnnouncementBody,
		type DouSection,
		type DouTerm,
		type DouAnnouncement,
		type DouApprovalRequest,
		type DouEnrollment,
		type AcademicGradeRow,
		type AcademicStudent,
		type AcademicExam,
		type DouClassroomOption,
		type DouMessage
	} from '$lib/apis/douAcademic';

	type PageMeta = { title: string; apiKey: string };

	const PAGES: Record<string, PageMeta> = {
		'/obs/akademisyen/subelerim': { title: 'Şubelerim', apiKey: 'sections' },
		'/obs/akademisyen/not-girisi': { title: 'Not Girişi', apiKey: 'grades-entry' },
		'/obs/akademisyen/yoklama-girisi': { title: 'Yoklama Girişi', apiKey: 'attendance-entry' },
		'/obs/akademisyen/sinav-tanimlama': { title: 'Sınav Tanımlama', apiKey: 'exam-define' },
		'/obs/akademisyen/danismanlik-ogrencilerim': {
			title: 'Danışmanlık Öğrencilerim',
			apiKey: 'advisees'
		},
		'/obs/akademisyen/onay-talepleri': { title: 'Onay Talepleri', apiKey: 'approvals' },
		'/obs/akademisyen/duyuru-olustur': { title: 'Duyuru Oluştur', apiKey: 'announce' },
		'/obs/akademisyen/mesajlar-gelen': { title: 'Gelen Mesajlar', apiKey: 'inbox' },
		'/obs/akademisyen/mesajlar-gonderilen': { title: 'Gönderilen Mesajlar', apiKey: 'sent' },
		'/obs/akademisyen/sifre-degistir': { title: 'Şifre Değiştir', apiKey: 'change-pw' }
	};

	$: activePath =
		($page.url.pathname || '/obs/akademisyen').replace(/\/+$/, '') || '/obs/akademisyen';
	$: meta = PAGES[activePath] ?? {
		title: ($page.params.path ?? '').replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
		apiKey: ''
	};
	$: pageTitle = meta.title;
	$: apiKey = meta.apiKey;

	// state
	let loading = false;
	let loadErr: string | null = null;

	let sections: DouSection[] = [];
	let terms: DouTerm[] = [];
	/** Şubelerim: seçili akademik dönem (ilk açılışta aktif dönem). */
	let selectedSectionsTermId = '';
	/** Not girişi: seçili akademik dönem (ilk açılışta aktif dönem); şube listesi buna göre filtrelenir. */
	let selectedGradesTermId = '';
	/** Sınav tanımlama: seçili akademik dönem (ilk açılışta aktif dönem); şube listesi buna göre filtrelenir. */
	let selectedExamsTermId = '';
	/** Yoklama girişi: seçili akademik dönem (ilk açılışta aktif dönem); şube listesi buna göre filtrelenir. */
	let selectedAttendanceTermId = '';
	let selectedSection = '';
	$: selectedSectionMeta =
		sections.find((s) => String(s.id) === String(selectedSection)) ?? null;
	$: examDefineTermRow =
		selectedSectionMeta && terms.length
			? terms.find((t) => t.id === selectedSectionMeta.term_id)
			: undefined;
	let sectionStudents: AcademicStudent[] = [];
	let gradeRows: AcademicGradeRow[] = [];
	let gradeEdits: Record<string, { midterm?: number; final?: number; makeup?: number; letter_grade?: string }> = {};
	let gradeDeletingId: string | null = null;
	let gradeSaving = false;
	let gradeSaved = false;
	let gradeWeights = { midterm_weight_percent: 40, final_weight_percent: 60 };
	let weightsSaving = false;
	let exams: AcademicExam[] = [];
	let examClassrooms: DouClassroomOption[] = [];
	let examClassroomsErr: string | null = null;
	let advisees: unknown[] = [];
	let adviseeDetailUserId: string | null = null;
	let adviseeEnrollments: DouEnrollment[] = [];
	let adviseeSchedBusy = false;
	let adviseeSchedErr: string | null = null;
	let activeTermId = '';
	let approvals: DouApprovalRequest[] = [];
	let inboxMsgs: DouMessage[] = [];
	let sentMsgs: DouMessage[] = [];
	/** Mesaj yaz — danışmanlık listesi */
	let msgAdvisees: { student_user_id: string; student_no: string; name: string }[] = [];
	let showAcademicCompose = false;
	/** Gelen kutusundan cevap: alıcı sabit */
	let academicComposeReplyTo: { userId: string; displayName: string } | null = null;
	let academicComposeRecipientMode: 'advisee' | 'section' = 'advisee';
	let academicComposeAdviseeId = '';
	let academicComposeSectionId = '';
	let academicComposeSectionStudents: AcademicStudent[] = [];
	let academicComposeSectionStudentUid = '';
	let academicComposeSubject = '';
	let academicComposeBody = '';
	let academicComposeSending = false;
	let academicComposeErr: string | null = null;
	let weekNoUi = '1';
	let attendanceStatus: Record<string, 'present' | 'absent' | 'excused'> = {};
	let weekCount = 14;
	let attendanceSaving = false;
	let attendanceSaved = false;
	let weekTouched = false;
	let attendanceLoadingWeek = false;

	function toDateOnly(s: unknown): Date | null {
		if (!s) return null;
		const d = new Date(String(s));
		return Number.isFinite(d.getTime()) ? d : null;
	}

	function weeksBetweenInclusive(start: Date, end: Date): number {
		// Gün farkını haftaya yuvarla; minimum 1.
		const ms = end.getTime() - start.getTime();
		const days = Math.floor(ms / (1000 * 60 * 60 * 24)) + 1;
		return Math.max(1, Math.ceil(days / 7));
	}

	function normalizeAttendanceUiStatus(
		raw: string | undefined | null
	): 'present' | 'absent' | 'excused' {
		const s = String(raw ?? '')
			.trim()
			.toLowerCase();
		if (s === 'absent' || s === 'yok') return 'absent';
		if (s === 'excused' || s === 'mazeret') return 'excused';
		return 'present';
	}

	function attendanceWeekStorageKey(sectionId: string) {
		return `obs-attendance-week:${sectionId}`;
	}

	function sortTermsNewestFirst(ts: DouTerm[]): DouTerm[] {
		return [...ts].sort((a, b) => {
			const ta = new Date(a.starts_at || 0).getTime();
			const tb = new Date(b.starts_at || 0).getTime();
			return tb - ta;
		});
	}

	function formatTermDropdownLabel(t: DouTerm): string {
		const name = (t.name ?? '').trim();
		if (name) return name;
		const bits = [t.academic_year, t.season].filter(Boolean);
		return bits.length ? bits.join(' ') : t.id;
	}

	$: termsSortedForSections = sortTermsNewestFirst(terms);

	/** Sınav sayfası optgroup: aktif işaretli dönem(ler) */
	$: examsTermsActive = termsSortedForSections.filter((t) => t.is_active);
	/** Aktif olmayan dönemler (yeniden eskiye) */
	$: examsTermsOther = termsSortedForSections.filter((t) => !t.is_active);

	function formatSectionExamChoice(s: DouSection): string {
		const secLetter = (s.section_code || '').trim() || String.fromCharCode(64 + (s.section_no || 1));
		const termLbl = (() => {
			const tid = s.term_id;
			if (!tid) return '';
			const te = terms.find((x) => x.id === tid);
			return te ? formatTermDropdownLabel(te) : '';
		})();
		const code = (s.course_code || '').trim();
		const name = (s.course_name || '').trim();
		const head = `[Şube ${secLetter}] ${code} — ${name}`;
		const tail: string[] = [];
		if (termLbl) tail.push(termLbl);
		const when = [s.day_of_week, s.start_time].filter(Boolean).join(' ');
		if (when) tail.push(when);
		const ec = s.enrollment_count;
		if (ec != null && Number.isFinite(ec)) tail.push(`${ec} öğrenci`);
		return tail.length ? `${head} · ${tail.join(' · ')}` : head;
	}

	function examTypeLabel(t: string): string {
		const m: Record<string, string> = {
			midterm: 'Vize',
			final: 'Final',
			makeup: 'Bütünleme',
			project: 'Proje'
		};
		return m[t] ?? t;
	}

	function pickTermRange(term: {
		starts_at?: string;
		ends_at?: string;
		start_date?: string;
		end_date?: string;
	}): { start: Date | null; end: Date | null } {
		// Backend farklı alan isimleri döndürebilir: starts_at/ends_at veya start_date/end_date
		const start = toDateOnly(term.starts_at ?? term.start_date);
		const end = toDateOnly(term.ends_at ?? term.end_date);
		return { start, end };
	}

	$: {
		// Şubenin term_id'sine göre dönem tarihini bul; yoksa 14 hafta fallback.
		const termId = (selectedSectionMeta as unknown as { term_id?: string } | null)?.term_id;
		const term = termId ? terms.find((t) => t.id === termId) : null;
		const { start, end } = term ? pickTermRange(term) : { start: null, end: null };
		const computed = start && end ? weeksBetweenInclusive(start, end) : 14;
		weekCount = Math.max(1, Math.min(30, computed));

		// Varsayılan hafta: bugün hangi haftaya denk geliyor? (dönem aralığı varsa)
		const today = new Date();
		const currentWeek =
			start && end
				? Math.max(1, Math.min(weekCount, weeksBetweenInclusive(start, new Date(Math.min(today.getTime(), end.getTime())))))
				: 1;

		// Kullanıcı elle değiştirmediyse seçimi güncelle; elle değiştirdiyse sadece clamp yap.
		const uiWeek = Number(weekNoUi) || 1;
		if (!weekTouched) weekNoUi = String(currentWeek);
		else if (uiWeek > weekCount) weekNoUi = String(weekCount);
		else if (uiWeek < 1) weekNoUi = '1';
	}

	// exam form
	let examForm = {
		exam_type: 'midterm',
		exam_date: '',
		exam_time: '09:00',
		classroom: '',
		weight_percent: 40
	};
	let examSaving = false;
	let examSaved = false;
	/** Düzenlenen sınav id; boşsa düzenleme yok */
	let editingExamId = '';
	let examEditForm = {
		exam_type: 'midterm',
		exam_date: '',
		exam_time: '09:00',
		classroom: '',
		weight_percent: 40
	};
	let examEditSaving = false;
	let deletingExamId = '';

	// announce form
	let annForm = {
		title: '',
		content: '',
		audience_type: 'section' as 'section' | 'advisees' | 'student' | 'all',
		section_id: '', // belirli şube
		student_no: '' // belirli öğrenci
	};
	let annSaving = false;
	let annSaved = false;
	let annErr: string | null = null;
	let myAnnouncements: DouAnnouncement[] = [];
	let editingAnnId = '';
	let annIsActive = true;

	let pwForm = { current_password: '', new_password: '', confirm_password: '' };
	let pwErr: string | null = null;
	let pwOk: string | null = null;
	let pwBusy = false;

	let gradeErr: string | null = null;
	let attendanceErr: string | null = null;
	let examErr: string | null = null;
	let approvalErr: string | null = null;

	/** obs_classrooms boş olsa bile tanımlı sınav satırlarındaki derslik metinlerini seçenek olarak birleştir */
	function mergeDouClassroomsWithExamStrings(
		base: DouClassroomOption[],
		examsList: AcademicExam[]
	): DouClassroomOption[] {
		const byCode = new Map<string, DouClassroomOption>();
		for (const c of base) {
			const k = (c.code ?? '').trim();
			if (k) byCode.set(k, c);
		}
		for (const ex of examsList) {
			const code = (ex.classroom ?? '').trim();
			if (!code || byCode.has(code)) continue;
			byCode.set(code, { id: '', code, label: code });
		}
		return [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code, 'tr'));
	}

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
			// Dönem listesi: Şubelerim / Not girişi / Sınav tanımlama / Yoklama girişi filtresi + yoklama haftası için
			if (
				!terms.length ||
				apiKey === 'sections' ||
				apiKey === 'grades-entry' ||
				apiKey === 'exam-define' ||
				apiKey === 'attendance-entry'
			) {
				const tr = await Promise.allSettled([getDouTerms(token)]);
				if (tr[0].status === 'fulfilled') {
					terms = (tr[0].value as DouTerm[]) ?? [];
				}
			}

			if (apiKey === 'sections') {
				if (!selectedSectionsTermId && terms.length) {
					const sorted = sortTermsNewestFirst(terms);
					selectedSectionsTermId =
						sorted.find((t) => t.is_active)?.id ?? sorted[0]?.id ?? '';
				}
			}

			if (apiKey === 'grades-entry') {
				if (!selectedGradesTermId && terms.length) {
					const sorted = sortTermsNewestFirst(terms);
					selectedGradesTermId =
						sorted.find((t) => t.is_active)?.id ?? sorted[0]?.id ?? '';
				}
			}

			if (apiKey === 'exam-define') {
				if (!selectedExamsTermId && terms.length) {
					const sorted = sortTermsNewestFirst(terms);
					selectedExamsTermId =
						sorted.find((t) => t.is_active)?.id ?? sorted[0]?.id ?? '';
				}
			}

			if (apiKey === 'attendance-entry') {
				if (!selectedAttendanceTermId && terms.length) {
					const sorted = sortTermsNewestFirst(terms);
					selectedAttendanceTermId =
						sorted.find((t) => t.is_active)?.id ?? sorted[0]?.id ?? '';
				}
			}

			const sectionsTermArg =
				apiKey === 'sections'
					? selectedSectionsTermId || undefined
					: apiKey === 'grades-entry'
						? selectedGradesTermId || undefined
						: apiKey === 'exam-define'
							? selectedExamsTermId || undefined
							: apiKey === 'attendance-entry'
								? selectedAttendanceTermId || undefined
								: undefined;
			/** Sunucu include_classrooms ile yanıt verdiyse /me/classrooms yedeğine gerek yok (proxy/HTML kırığından kaçın) */
			let sectionsPayloadHadClassrooms = false;
			const secRes = await Promise.allSettled([
				getDouAcademicSections(token, sectionsTermArg, {
					includeClassrooms: apiKey === 'exam-define'
				})
			]);
			if (secRes[0].status === 'fulfilled') {
				const pack = secRes[0].value;
				sections = pack.sections ?? [];
				if (apiKey === 'exam-define') {
					sectionsPayloadHadClassrooms = Object.prototype.hasOwnProperty.call(pack, 'classrooms');
					examClassrooms = pack.classrooms ?? [];
					if (pack.classrooms?.length) examClassroomsErr = null;
				}
			} else {
				sections = [];
				if (apiKey === 'exam-define') examClassrooms = [];
			}
			if (apiKey === 'grades-entry' && selectedSection) {
				const sectionIds = new Set(sections.map((s) => s.id));
				if (!sectionIds.has(selectedSection)) selectedSection = '';
			}
			if (apiKey === 'exam-define' && selectedSection) {
				const sectionIds = new Set(sections.map((s) => s.id));
				if (!sectionIds.has(selectedSection)) selectedSection = '';
			}
			if (apiKey === 'attendance-entry' && selectedSection) {
				const sectionIds = new Set(sections.map((s) => s.id));
				if (!sectionIds.has(selectedSection)) selectedSection = '';
			}
			if (!selectedSection && sections.length) selectedSection = sections[0].id;

			if (apiKey === 'grades-entry') {
				// Şube listesi (GET /me/sections) doğru ağırlığı taşır. GET /grades içindeki section bazen 40/60
				// varsayılanı dönüyor; `??` zinciri sec önce yazılırsa 40 sayısı listeyi ezer — önce listRow.
				const listRow = sections.find((s) => String(s.id) === String(selectedSection));
				if (listRow) {
					gradeWeights = {
						midterm_weight_percent: Number(listRow.midterm_weight_percent ?? 40),
						final_weight_percent: Number(listRow.final_weight_percent ?? 60)
					};
				}

				if (selectedSection) {
					const r = await Promise.allSettled([getDouSectionGrades(token, selectedSection)]);
					if (r[0].status === 'fulfilled') {
						const payload = r[0].value;
						gradeRows = payload.students ?? [];
						const sec = payload.section ?? null;
						if (sec) {
							const mid = listRow?.midterm_weight_percent ?? sec.midterm_weight_percent;
							const fin = listRow?.final_weight_percent ?? sec.final_weight_percent;
							const midW = Number(mid ?? 40);
							const finW = Number(fin ?? 60);
							gradeWeights = {
								midterm_weight_percent: midW,
								final_weight_percent: finW
							};
							sections = sections.map((s) =>
								String(s.id) === String(selectedSection)
									? ({
											...s,
											...sec,
											midterm_weight_percent: midW,
											final_weight_percent: finW
										} as DouSection)
									: s
							);
						}
					} else {
						gradeRows = [];
					}
				} else {
					gradeRows = [];
				}
				gradeEdits = {};
				gradeRows.forEach((row) => {
					gradeEdits[row.enrollment_id] = {
						midterm: row.midterm ?? undefined,
						final: row.final ?? undefined,
						makeup: row.makeup ?? undefined,
						letter_grade: row.letter_grade?.trim() ?? ''
					};
				});
				// İlk yüklemede de otomatik harf notunu hesapla
				recalcAllLetters();
			}
			if (apiKey === 'attendance-entry') {
				if (selectedSection) {
					const wkKey = attendanceWeekStorageKey(selectedSection);
					const savedWeek = browser ? sessionStorage.getItem(wkKey) : null;
					if (savedWeek != null && /^[1-9][0-9]*$/.test(savedWeek)) {
						weekTouched = true;
						weekNoUi = savedWeek;
					} else {
						weekTouched = false;
					}
					const r = await Promise.allSettled([getDouSectionStudents(token, selectedSection)]);
					if (r[0].status === 'fulfilled') {
						sectionStudents =
							(r[0].value as unknown as { students: AcademicStudent[] }).students ?? [];
					} else {
						sectionStudents = [];
					}
					sectionStudents.forEach((s) => {
						attendanceStatus[s.enrollment_id] = attendanceStatus[s.enrollment_id] ?? 'present';
					});
					// İlk açılışta seçili haftanın mevcut kayıtlarını yükle
					await loadAttendanceWeek();
				} else {
					// Dönem değişti ve bu dönemde şube yok → eski liste kalmasın
					sectionStudents = [];
					attendanceStatus = {};
				}
			}
			if (apiKey === 'exam-define') {
				editingExamId = '';
				if (!examClassrooms.length && !sectionsPayloadHadClassrooms) {
					examClassroomsErr = null;
					const cr = await Promise.allSettled([getDouAcademicClassrooms(token)]);
					if (cr[0].status === 'fulfilled') {
						examClassrooms = cr[0].value.classrooms ?? [];
					} else {
						examClassrooms = [];
						const reason = cr[0].reason;
						examClassroomsErr =
							reason instanceof Error
								? reason.message
								: 'Derslik listesi yüklenemedi (sunucu veya oturum).';
					}
				} else if (sectionsPayloadHadClassrooms) {
					examClassroomsErr = null;
				}
				if (selectedSection) {
					const er = await Promise.allSettled([
						getDouSectionExams(token, selectedSection)
					]);
					exams = er[0].status === 'fulfilled' ? (er[0].value.exams ?? []) : [];
				} else {
					exams = [];
				}
				examClassrooms = mergeDouClassroomsWithExamStrings(examClassrooms, exams);
				if (examClassrooms.length) examClassroomsErr = null;
			}
			if (apiKey === 'advisees') {
				const r = await Promise.allSettled([
					getDouAcademicAdvisees(token),
					getDouTerms(token)
				]);
				if (r[0].status === 'fulfilled') advisees = r[0].value.advisees ?? [];
				else advisees = [];
				if (r[1].status === 'fulfilled') {
					const tl = r[1].value;
					activeTermId = tl.find((t) => t.is_active)?.id ?? tl[tl.length - 1]?.id ?? '';
				} else {
					activeTermId = '';
				}
				adviseeDetailUserId = null;
				adviseeEnrollments = [];
			}
			if (apiKey === 'approvals') {
				const r = await Promise.allSettled([getDouAcademicApprovalRequests(token)]);
				if (r[0].status === 'fulfilled') approvals = r[0].value.requests ?? [];
			}
			if (apiKey === 'announce') {
				const r = await Promise.allSettled([getDouAcademicAnnouncements(token)]);
				if (r[0].status === 'fulfilled') myAnnouncements = r[0].value.announcements ?? [];
				else myAnnouncements = [];
			}
			if (apiKey === 'inbox' || apiKey === 'sent') {
				const msgFetch = apiKey === 'inbox' ? getDouInbox(token) : getDouSent(token);
				const r = await Promise.allSettled([msgFetch, getDouAcademicAdvisees(token)]);
				if (r[0].status === 'fulfilled') {
					if (apiKey === 'inbox') inboxMsgs = r[0].value.messages ?? [];
					else sentMsgs = r[0].value.messages ?? [];
				}
				if (r[1].status === 'fulfilled') {
					const raw = r[1].value.advisees ?? [];
					msgAdvisees = raw
						.map((a: Record<string, unknown>) => ({
							student_user_id: String(a.student_user_id ?? ''),
							student_no: String(a.student_no ?? ''),
							name: String(a.name ?? '')
						}))
						.filter((a) => a.student_user_id);
				} else {
					msgAdvisees = [];
				}
			}
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'API hatası.';
		} finally {
			loading = false;
		}
	}

	function resetAcademicCompose() {
		academicComposeReplyTo = null;
		academicComposeRecipientMode = 'advisee';
		academicComposeAdviseeId = '';
		academicComposeSectionId = '';
		academicComposeSectionStudents = [];
		academicComposeSectionStudentUid = '';
		academicComposeSubject = '';
		academicComposeBody = '';
		academicComposeErr = null;
	}

	function openAcademicNewMessage() {
		resetAcademicCompose();
		showAcademicCompose = true;
	}

	async function openAcademicReply(m: DouMessage) {
		const sid = m.sender_user_id;
		if (!sid) {
			academicComposeErr = 'Gönderen kimliği eksik; cevap verilemiyor.';
			return;
		}
		resetAcademicCompose();
		academicComposeReplyTo = {
			userId: sid,
			displayName: m.sender_name?.trim() || 'Öğrenci'
		};
		academicComposeSubject = (m.subject || '').startsWith('Re:')
			? m.subject
			: `Re: ${m.subject || '(konu yok)'}`;
		academicComposeBody = '';
		showAcademicCompose = true;
		const token = localStorage.token ?? null;
		if (token) void markDouMessageRead(token, m.id).catch(() => {});
	}

	async function onAcademicComposeSectionChange() {
		academicComposeSectionStudents = [];
		academicComposeSectionStudentUid = '';
		if (!browser || !academicComposeSectionId) return;
		const token = localStorage.token ?? null;
		if (!token) return;
		try {
			const r = await getDouSectionStudents(token, academicComposeSectionId);
			academicComposeSectionStudents =
				(r as unknown as { students?: AcademicStudent[] }).students ?? [];
		} catch {
			academicComposeSectionStudents = [];
		}
	}

	async function sendAcademicMessage() {
		academicComposeSending = true;
		academicComposeErr = null;
		const token = localStorage.token ?? null;
		try {
			if (!token) {
				academicComposeErr = 'Giriş yapmanız gerekiyor.';
				return;
			}
			let receiverId = '';
			let receiverName = '';
			if (academicComposeReplyTo) {
				receiverId = academicComposeReplyTo.userId;
				receiverName = academicComposeReplyTo.displayName;
			} else if (academicComposeRecipientMode === 'advisee') {
				receiverId = academicComposeAdviseeId;
				const adv = msgAdvisees.find((a) => a.student_user_id === receiverId);
				receiverName = adv ? `${adv.name} (${adv.student_no})` : '';
			} else {
				receiverId = academicComposeSectionStudentUid;
				const st = academicComposeSectionStudents.find(
					(s) => (s.student_user_id || '') === receiverId
				);
				receiverName = st ? `${st.name} (${st.student_no})` : '';
			}
			if (!receiverId) {
				academicComposeErr = 'Alıcı seçin (danışmanlık öğrencisi veya şube).';
				return;
			}
			if (!academicComposeSubject.trim() || !academicComposeBody.trim()) {
				academicComposeErr = 'Konu ve mesaj gerekli.';
				return;
			}
			await sendDouMessageApi(token, {
				receiver_user_id: receiverId,
				receiver_name: receiverName || 'Öğrenci',
				receiver_type: 'ogrenci',
				subject: academicComposeSubject.trim(),
				body: academicComposeBody.trim()
			});
			showAcademicCompose = false;
			resetAcademicCompose();
			await loadPage();
		} catch (e: unknown) {
			academicComposeErr = e instanceof Error ? e.message : 'Gönderilemedi.';
		} finally {
			academicComposeSending = false;
		}
	}

	function adviseeGpaTextClass(gpa: number): string {
		return gpa >= 2.0
			? 'text-emerald-600 dark:text-emerald-400'
			: 'text-red-600 dark:text-red-400';
	}

	function cancelEditAnn() {
		editingAnnId = '';
		annIsActive = true;
		annForm = {
			title: '',
			content: '',
			audience_type: 'section',
			section_id: '',
			student_no: ''
		};
	}

	function startEditAnn(a: DouAnnouncement) {
		annErr = null;
		editingAnnId = a.id;
		const at = (a.audience_type || 'section') as typeof annForm.audience_type;
		annForm = {
			title: a.title,
			content: a.content,
			audience_type: at,
			section_id: a.course_section_id ?? '',
			student_no: (a.student_no ?? '').trim()
		};
		annIsActive = a.is_active !== false;
	}

	async function removeAnn(id: string) {
		if (!browser || !confirm('Bu duyuruyu silmek istediğinize emin misiniz?')) return;
		const token = localStorage.token ?? null;
		annErr = null;
		try {
			await deleteDouAcademicAnnouncement(token, id);
			myAnnouncements = myAnnouncements.filter((x) => x.id !== id);
			if (editingAnnId === id) cancelEditAnn();
		} catch (e: unknown) {
			annErr = e instanceof Error ? e.message : 'Silinemedi.';
		}
	}

	afterNavigate(async (navigation) => {
		await tick();
		if (!browser) return;
		const toPath =
			(navigation.to?.url.pathname || '').replace(/\/+$/, '') || '/obs/akademisyen';
		const fromPath = (navigation.from?.url.pathname || '').replace(/\/+$/, '') || '';
		if (toPath === '/obs/akademisyen/subelerim' && fromPath !== toPath) {
			selectedSectionsTermId = '';
		}
		if (toPath === '/obs/akademisyen/not-girisi' && fromPath !== toPath) {
			selectedGradesTermId = '';
		}
		if (toPath === '/obs/akademisyen/sinav-tanimlama' && fromPath !== toPath) {
			selectedExamsTermId = '';
		}
		if (toPath === '/obs/akademisyen/yoklama-girisi' && fromPath !== toPath) {
			selectedAttendanceTermId = '';
			selectedSection = '';
			sectionStudents = [];
			attendanceStatus = {};
		}
		void loadPage();
	});

	const LETTER_GRADE_OPTIONS = [
		'',
		'A+',
		'A',
		'B+',
		'B',
		'C+',
		'C',
		'D+',
		'D',
		'F',
		'M',
		'S',
		'DZ',
		'G',
		'K',
		'TKR',
		'AA',
		'BA',
		'BB',
		'CB',
		'CC',
		'DC',
		'DD',
		'FD',
		'FF',
		'GR',
		'İ'
	];

	/** Svelte {#if} içinde `!==` vb. ifadeler bazı sürümlerde `>` ile ayrıştırma hatası verebiliyor */
	function needsCustomLetterOption(enrollmentId: string): boolean {
		const lg = (gradeEdits[enrollmentId]?.letter_grade ?? '').trim();
		return lg.length > 0 && !LETTER_GRADE_OPTIONS.includes(lg);
	}

	async function saveGrades() {
		gradeSaving = true;
		gradeErr = null;
		const token = localStorage.token ?? null;
		try {
			const grades = Object.entries(gradeEdits).map(([enrollment_id, g]) => ({
				enrollment_id,
				midterm: g.midterm,
				final: g.final,
				makeup: g.makeup,
				// Harf notunu backend de hesaplayabiliyor; yine de UI'daki değeri gönderiyoruz
				letter_grade: (g.letter_grade ?? '').trim()
			}));
			await putDouSectionGrades(token, selectedSection, grades);
			gradeSaved = true;
			setTimeout(() => {
				gradeSaved = false;
			}, 3500);
			// Backend tarafında hesaplanan harf notu / finalize bilgisi ekrana yansısın
			await loadPage();
		} catch (e: unknown) {
			console.error('[NOT kaydet] PUT /grades hatası', {
				section_id: selectedSection,
				message: e instanceof Error ? e.message : String(e),
				err: e
			});
			gradeErr = e instanceof Error ? e.message : 'Notlar kaydedilemedi.';
		} finally {
			gradeSaving = false;
		}
	}

	async function removeStudentGrade(enrollmentId: string) {
		if (!browser || !confirm('Bu öğrencinin not kaydını (vize/final/harf) silmek istiyor musunuz?')) return;
		const token = localStorage.token ?? null;
		if (!token || !selectedSection) return;
		gradeErr = null;
		gradeDeletingId = enrollmentId;
		try {
			await deleteDouSectionGrade(token, selectedSection, enrollmentId);
			await loadPage();
		} catch (e: unknown) {
			gradeErr = e instanceof Error ? e.message : 'Not silinemedi.';
		} finally {
			gradeDeletingId = null;
		}
	}

	async function finalizeGrades() {
		const token = localStorage.token ?? null;
		gradeErr = null;
		try {
			console.log('[NOT kesinleştir] POST /grades/finalize', {
				section_id: selectedSection
			});
			await finalizeDouSectionGrades(token, selectedSection);
			gradeSaved = true;
			setTimeout(() => {
				gradeSaved = false;
			}, 3500);
			await loadPage();
		} catch (e: unknown) {
			console.error('[NOT kesinleştir] sunucu hatası', {
				section_id: selectedSection,
				message: e instanceof Error ? e.message : String(e),
				err: e
			});
			gradeErr = e instanceof Error ? e.message : 'Notlar kesinleştirilemedi.';
		}
	}

	function clampPct(x: unknown, fallback: number) {
		const n = Number(x);
		if (!Number.isFinite(n)) return fallback;
		return Math.max(0, Math.min(100, n));
	}

	function letterFromScore(score: number): string {
		if (score >= 95) return 'A+';
		if (score >= 90) return 'A';
		if (score >= 85) return 'B+';
		if (score >= 75) return 'B';
		if (score >= 65) return 'C+';
		if (score >= 55) return 'C';
		if (score >= 45) return 'D+';
		if (score >= 40) return 'D';
		return 'F';
	}

	function recalcLetter(enrollmentId: string) {
		const g = gradeEdits[enrollmentId];
		if (!g) return;
		const mid = g.midterm;
		const fin = g.final;
		const makeup = g.makeup;

		if (mid == null || (fin == null && makeup == null)) {
			g.letter_grade = '';
			return;
		}

		let wMid = clampPct(gradeWeights.midterm_weight_percent, 40);
		let wFin = clampPct(gradeWeights.final_weight_percent, 60);
		if (wMid + wFin <= 0) {
			wMid = 40;
			wFin = 60;
		}

		// Eğer büt girilmişse final yerine büt kullanılır (ağırlığı aynı)
		const effectiveFinal = (makeup !== null && makeup !== undefined) ? makeup : (fin ?? 0);
		const score = (Number(mid) * wMid + Number(effectiveFinal) * wFin) / 100;
		g.letter_grade = letterFromScore(score);
	}

	function recalcAllLetters() {
		for (const row of gradeRows) recalcLetter(row.enrollment_id);
	}

	async function saveWeights() {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token || !selectedSection) return;
		const wMid = clampPct(gradeWeights.midterm_weight_percent, 40);
		const wFin = clampPct(gradeWeights.final_weight_percent, 60);
		if (wMid + wFin !== 100) {
			gradeErr = 'Vize/Final etkisi toplamı %100 olmalı.';
			return;
		}
		weightsSaving = true;
		gradeErr = null;
		try {
			const body = {
				midterm_weight_percent: wMid,
				final_weight_percent: wFin
			};
			const r = await putDouSectionGradeWeights(token, selectedSection, body);
			if (r.section) {
				sections = sections.map((s) =>
					String(s.id) === String(selectedSection)
						? ({
								...s,
								...r.section,
								midterm_weight_percent: wMid,
								final_weight_percent: wFin
							} as DouSection)
						: s
				);
			}
			recalcAllLetters();
			gradeSaved = true;
			setTimeout(() => (gradeSaved = false), 2500);
		} catch (e: unknown) {
			gradeErr = e instanceof Error ? e.message : 'Ağırlıklar kaydedilemedi.';
		} finally {
			weightsSaving = false;
		}
	}


	async function saveAttendance() {
		const token = localStorage.token ?? null;
		attendanceErr = null;
		attendanceSaved = false;
		attendanceSaving = true;
		if (!token || !selectedSection) {
			attendanceErr = 'Oturum veya şube seçimi yok.';
			attendanceSaving = false;
			return;
		}
		const week = Number(weekNoUi) || 1;
		if (!Number.isFinite(week) || week < 1) {
			attendanceErr = 'Hafta seçimi geçersiz.';
			attendanceSaving = false;
			return;
		}
		const records = Object.entries(attendanceStatus).map(([enrollment_id, status]) => ({
			enrollment_id,
			status
		}));
		try {
			await putDouSectionAttendance(token, selectedSection, week, records);
			if (browser) {
				sessionStorage.setItem(attendanceWeekStorageKey(selectedSection), String(week));
			}
			attendanceSaved = true;
			setTimeout(() => (attendanceSaved = false), 3000);
			await loadAttendanceWeek();
		} catch (e: unknown) {
			attendanceErr = e instanceof Error ? e.message : 'Yoklama kaydedilemedi.';
		} finally {
			attendanceSaving = false;
		}
	}

	async function loadAttendanceWeek() {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token || !selectedSection) return;
		const week = Number(weekNoUi) || 1;
		attendanceErr = null;
		attendanceLoadingWeek = true;
		try {
			const r = await getDouSectionAttendance(token, selectedSection, week);
			const map: Record<string, 'present' | 'absent' | 'excused'> = {};
			for (const rec of r.records ?? []) {
				map[rec.enrollment_id] = normalizeAttendanceUiStatus(rec.status);
			}
			// Listedeki öğrenciler için set et; kayıt yoksa default present
			for (const s of sectionStudents) {
				attendanceStatus[s.enrollment_id] = map[s.enrollment_id] ?? 'present';
			}
		} catch (e: unknown) {
			attendanceErr = e instanceof Error ? e.message : 'Yoklama yüklenemedi.';
		} finally {
			attendanceLoadingWeek = false;
		}
	}

	async function createExam() {
		examSaving = true;
		examErr = null;
		const token = localStorage.token ?? null;
		if (!token || !selectedSection) {
			examErr = !token ? 'Oturum bulunamadı; yeniden giriş yapın.' : 'Önce bir şube seçin.';
			examSaving = false;
			return;
		}
		const dateTrim = (examForm.exam_date ?? '').trim();
		if (!dateTrim) {
			examErr = 'Sınav tarihi zorunludur. Lütfen takvimden bir tarih seçin.';
			examSaving = false;
			return;
		}
		const w = Number(examForm.weight_percent);
		if (!Number.isFinite(w) || w <= 0 || w > 100) {
			examErr = 'Ağırlık yüzdesi 1 ile 100 arasında bir sayı olmalıdır.';
			examSaving = false;
			return;
		}
		try {
			await createDouSectionExam(token, selectedSection, {
				exam_type: examForm.exam_type,
				exam_date: examForm.exam_date,
				exam_time: examForm.exam_time,
				weight_percent: Number(examForm.weight_percent),
				...(examForm.classroom?.trim()
					? { classroom: examForm.classroom.trim() }
					: {})
			});
			const sync = await getDouSectionExams(token, selectedSection);
			exams = sync.exams ?? [];
			examSaved = true;
			examForm = {
				exam_type: 'midterm',
				exam_date: '',
				exam_time: '09:00',
				classroom: '',
				weight_percent: 40
			};
			setTimeout(() => {
				examSaved = false;
			}, 3500);
		} catch (e: unknown) {
			examErr = e instanceof Error ? e.message : 'Sınav eklenemedi.';
		} finally {
			examSaving = false;
		}
	}

	function examTimeForInput(t: string): string {
		if (!t) return '09:00';
		const s = String(t).trim();
		if (s.length >= 8 && s[2] === ':' && s[5] === ':') return s.slice(0, 5);
		if (s.length >= 5 && s[2] === ':') return s.slice(0, 5);
		return '09:00';
	}

	function openExamEdit(ex: AcademicExam) {
		examErr = null;
		editingExamId = ex.id;
		examEditForm = {
			exam_type: ex.exam_type,
			exam_date: (ex.exam_date || '').slice(0, 10),
			exam_time: examTimeForInput(ex.exam_time || ''),
			classroom: ex.classroom ?? '',
			weight_percent: Number(ex.weight_percent ?? 40)
		};
	}

	function cancelExamEdit() {
		editingExamId = '';
		examErr = null;
	}

	async function saveExamEdit() {
		if (!editingExamId || !selectedSection) return;
		const token = localStorage.token ?? null;
		examEditSaving = true;
		examErr = null;
		try {
			const updated = await updateDouSectionExam(token, selectedSection, editingExamId, {
				exam_type: examEditForm.exam_type,
				exam_date: examEditForm.exam_date,
				exam_time: examEditForm.exam_time,
				classroom: examEditForm.classroom?.trim() ? examEditForm.classroom.trim() : null,
				weight_percent: Number(examEditForm.weight_percent)
			});
			exams = exams.map((e) => (e.id === updated.id ? updated : e));
			editingExamId = '';
		} catch (e: unknown) {
			examErr = e instanceof Error ? e.message : 'Sınav güncellenemedi.';
		} finally {
			examEditSaving = false;
		}
	}

	async function removeExam(ex: AcademicExam) {
		if (!browser) return;
		if (!confirm(`Bu sınavı silmek istediğinize emin misiniz? (${ex.exam_date} ${ex.exam_time})`))
			return;
		const token = localStorage.token ?? null;
		deletingExamId = ex.id;
		examErr = null;
		try {
			await deleteDouSectionExam(token, selectedSection, ex.id);
			exams = exams.filter((e) => e.id !== ex.id);
			if (editingExamId === ex.id) editingExamId = '';
		} catch (e: unknown) {
			examErr = e instanceof Error ? e.message : 'Sınav silinemedi.';
		} finally {
			deletingExamId = '';
		}
	}

	async function resolveApproval(id: string, action: 'approve' | 'reject') {
		const token = localStorage.token ?? null;
		approvalErr = null;
		try {
			await resolveDouApprovalRequest(token, id, action);
			approvals = approvals.map((r) =>
				r.id === id ? { ...r, status: action === 'approve' ? 'approved' : 'rejected' } : r
			);
		} catch (e: unknown) {
			approvalErr = e instanceof Error ? e.message : 'İşlem yapılamadı.';
		}
	}

	async function loadAdviseeEnrollments(studentUserId: string) {
		adviseeDetailUserId = studentUserId;
		adviseeSchedErr = null;
		const token = localStorage.token ?? null;
		if (!token || !activeTermId) {
			adviseeEnrollments = [];
			adviseeSchedErr = !activeTermId ? 'Aktif dönem yok.' : 'Oturum yok.';
			return;
		}
		adviseeSchedBusy = true;
		try {
			const r = await getDouAdviseeEnrollments(token, studentUserId, activeTermId);
			adviseeEnrollments = r.enrollments ?? [];
		} catch (e: unknown) {
			adviseeSchedErr = e instanceof Error ? e.message : 'Yüklenemedi.';
			adviseeEnrollments = [];
		} finally {
			adviseeSchedBusy = false;
		}
	}

	async function runFinalizeSched(studentUserId: string) {
		const token = localStorage.token ?? null;
		adviseeSchedErr = null;
		if (!token || !activeTermId) return;
		adviseeSchedBusy = true;
		try {
			await finalizeDouAdviseeSchedule(token, studentUserId, activeTermId);
			await loadAdviseeEnrollments(studentUserId);
		} catch (e: unknown) {
			adviseeSchedErr = e instanceof Error ? e.message : 'Kesinleştirilemedi.';
		} finally {
			adviseeSchedBusy = false;
		}
	}

	async function runRejectSched(studentUserId: string) {
		const token = localStorage.token ?? null;
		adviseeSchedErr = null;
		if (!token || !activeTermId) return;
		adviseeSchedBusy = true;
		try {
			await rejectDouAdviseeSchedule(token, studentUserId, activeTermId);
			await loadAdviseeEnrollments(studentUserId);
		} catch (e: unknown) {
			adviseeSchedErr = e instanceof Error ? e.message : 'İşlem yapılamadı.';
		} finally {
			adviseeSchedBusy = false;
		}
	}

	async function changePassword() {
		pwBusy = true;
		pwErr = null;
		pwOk = null;
		const token = localStorage.token ?? null;
		if (!token) {
			pwErr = 'Oturum yok.';
			pwBusy = false;
			return;
		}
		if (!pwForm.current_password || !pwForm.new_password) {
			pwErr = 'Tüm alanlar zorunlu.';
			pwBusy = false;
			return;
		}
		if (pwForm.new_password !== pwForm.confirm_password) {
			pwErr = 'Şifreler eşleşmiyor.';
			pwBusy = false;
			return;
		}
		if (pwForm.new_password.length < 8) {
			pwErr = 'En az 8 karakter olmalı.';
			pwBusy = false;
			return;
		}
		try {
			await updateUserPassword(token, pwForm.current_password, pwForm.new_password);
			pwOk = 'Şifre güncellendi.';
			pwForm = { current_password: '', new_password: '', confirm_password: '' };
		} catch (e: unknown) {
			let msg = 'Şifre güncellenemedi.';
			if (typeof e === 'string') msg = e;
			else if (e instanceof Error) msg = e.message;
			else if (e && typeof e === 'object' && 'detail' in e) {
				const d = (e as { detail?: unknown }).detail;
				msg = typeof d === 'string' ? d : JSON.stringify(d);
			}
			pwErr = msg;
		} finally {
			pwBusy = false;
		}
	}
</script>

<svelte:head><title>OBS — {pageTitle}</title></svelte:head>

<ObsShell {activePath} role="akademisyen">
	<span slot="userline">{$user?.name ?? 'Akademisyen'} • {pageTitle}</span>

	<div class="space-y-4">
		<!-- Başlık -->
		<div
			class="rounded-xl border border-black/10 bg-white px-5 py-4 shadow-sm dark:border-white/10 dark:bg-white/5"
		>
			<h1 class="text-base font-bold text-slate-800 dark:text-slate-100">{pageTitle}</h1>
		</div>

		{#if loading}
			<div
				class="flex items-center justify-center rounded-xl border border-black/10 bg-white p-12 dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="h-6 w-6 animate-spin rounded-full border-2 border-sky-500 border-t-transparent"
				></div>
				<span class="ml-3 text-sm text-slate-400">Yükleniyor…</span>
			</div>
		{:else if loadErr}
			<div
				class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900/40 dark:bg-amber-950/30"
			>
				<div class="text-sm font-semibold text-amber-900 dark:text-amber-100">Hata</div>
				<div class="mt-1 text-xs text-amber-700 dark:text-amber-300">{loadErr}</div>
			</div>

			<!-- ============================================================ -->
			<!-- ŞUBELERİM                                                    -->
			<!-- ============================================================ -->
		{:else if apiKey === 'sections'}
			<div class="flex flex-wrap items-center gap-3">
				<span class="text-xs font-semibold text-slate-500">Akademik dönem:</span>
				<select
					bind:value={selectedSectionsTermId}
					on:change={() => loadPage()}
					class="min-w-[14rem] rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
				>
					{#each termsSortedForSections as t}
						<option value={t.id}>{formatTermDropdownLabel(t)}</option>
					{/each}
				</select>
			</div>

			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="grid grid-cols-6 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
				>
					<div class="col-span-2">Ders</div>
					<div>Dönem</div>
					<div>Gün</div>
					<div>Saat</div>
					<div>Derslik</div>
				</div>
				{#each sections as s}
					<div
						class="grid grid-cols-6 border-t border-black/5 px-5 py-3.5 text-sm dark:border-white/10 hover:bg-slate-50/50 transition-colors"
					>
						<div class="col-span-2">
							<span class="font-mono text-xs font-semibold text-slate-500">{s.course_code}</span>
							<span class="ml-2 font-medium">{s.course_name}</span>
						</div>
						<div class="text-slate-500 text-xs">{s.term_name ?? '—'}</div>
						<div class="text-slate-500">{s.day_of_week ?? '—'}</div>
						<div class="text-slate-500">{s.start_time ?? '—'}</div>
						<div class="text-slate-500 text-xs">{s.classroom_code ?? '—'}</div>
					</div>
				{:else}
					<div class="px-5 py-8 text-center text-sm text-slate-400">Şube bulunamadı.</div>
				{/each}
			</div>

			<!-- ============================================================ -->
			<!-- NOT GİRİŞİ                                                   -->
			<!-- ============================================================ -->
		{:else if apiKey === 'grades-entry'}
			<div class="flex flex-wrap items-center gap-3">
				<span class="text-xs font-semibold text-slate-500">Akademik dönem:</span>
				<select
					bind:value={selectedGradesTermId}
					on:change={() => loadPage()}
					class="min-w-[14rem] rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
				>
					{#each termsSortedForSections as t}
						<option value={t.id}>{formatTermDropdownLabel(t)}</option>
					{/each}
				</select>
				<span class="text-xs font-semibold text-slate-500">Şube:</span>
				<select
					bind:value={selectedSection}
					on:change={() => loadPage()}
					class="min-w-[12rem] rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5"
				>
					{#each sections as s}
						<option value={s.id}>{s.course_code} — {s.course_name}</option>
					{/each}
				</select>
				{#if selectedSectionMeta}
					<span class="text-xs text-slate-500">
						<strong class="text-slate-700 dark:text-slate-200">{selectedSectionMeta.course_code}</strong>
						— {selectedSectionMeta.course_name} · Şube {selectedSectionMeta.section_no}
						{#if selectedSectionMeta.day_of_week}
							· {selectedSectionMeta.day_of_week} {selectedSectionMeta.start_time}
						{/if}
					</span>
				{/if}
			</div>

			<!-- Vize/Final etkisi -->
			<div
				class="rounded-xl border border-black/10 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="flex flex-wrap items-end gap-3">
					<div class="text-sm font-semibold text-slate-800 dark:text-slate-100">Not girişi ayarları</div>
					<div class="ml-auto text-xs text-slate-400">Toplam %100 olmalı</div>
				</div>
				<div class="mt-3 flex flex-wrap items-end gap-3">
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Vize etkisi %</div>
						<input
							type="number"
							min="0"
							max="100"
							step="1"
							bind:value={gradeWeights.midterm_weight_percent}
							on:input={() => recalcAllLetters()}
							class="w-28 rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						/>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Final etkisi %</div>
						<input
							type="number"
							min="0"
							max="100"
							step="1"
							bind:value={gradeWeights.final_weight_percent}
							on:input={() => recalcAllLetters()}
							class="w-28 rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						/>
					</label>
					<button
						type="button"
						on:click={saveWeights}
						disabled={weightsSaving}
						class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-500 disabled:opacity-50"
					>
						{weightsSaving ? 'Kaydediliyor…' : 'Ağırlıkları Kaydet'}
					</button>
				</div>
			</div>

			{#if gradeSaved}
				<div
					class="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
				>
					Notlar kaydedildi.
				</div>
			{/if}
			{#if gradeErr}
				<div
					class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
				>
					{gradeErr}
				</div>
			{/if}

			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Öğrenci</th>
								<th class="px-4 py-3 text-left">No</th>
								<th class="px-4 py-3 text-center w-28">Vize</th>
								<th class="px-4 py-3 text-center w-28">Final</th>
								<th class="px-4 py-3 text-center w-28">Büt</th>
								<th class="px-4 py-3 text-center min-w-[7rem]">Harf</th>
								<th class="px-4 py-3 text-center">Durum</th>
								<th class="px-4 py-3 text-center w-24">İşlem</th>
							</tr>
						</thead>
						<tbody>
							{#each gradeRows as g}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-2.5 font-medium">{g.name}</td>
									<td class="px-4 py-2.5 font-mono text-xs text-slate-400">{g.student_no}</td>
									<td class="px-4 py-2.5">
										<input
											type="number"
											min="0"
											max="100"
											step="0.5"
											bind:value={gradeEdits[g.enrollment_id].midterm}
											disabled={g.is_finalized}
											on:input={() => recalcLetter(g.enrollment_id)}
											class="w-full rounded-lg border border-black/10 bg-white px-2 py-1 text-center text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
										/>
									</td>
									<td class="px-4 py-2.5">
										<input
											type="number"
											min="0"
											max="100"
											step="0.5"
											bind:value={gradeEdits[g.enrollment_id].final}
											disabled={g.is_finalized}
											on:input={() => recalcLetter(g.enrollment_id)}
											class="w-full rounded-lg border border-black/10 bg-white px-2 py-1 text-center text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
										/>
									</td>
									<td class="px-4 py-2.5">
										<input
											type="number"
											min="0"
											max="100"
											step="0.5"
											bind:value={gradeEdits[g.enrollment_id].makeup}
											disabled={g.is_finalized}
											on:input={() => recalcLetter(g.enrollment_id)}
											class="w-full rounded-lg border-2 border-amber-200 bg-amber-50/30 px-2 py-1 text-center text-sm font-bold outline-none focus:border-amber-500 focus:ring-0 dark:border-amber-900/40 dark:bg-amber-900/10 dark:text-amber-200"
											placeholder="—"
										/>
									</td>
									<td class="px-4 py-2.5 text-center">
										<span
											class="rounded-full px-2 py-0.5 text-xs font-bold {g.is_finalized
												? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
												: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300'}"
										>
											{(gradeEdits[g.enrollment_id].letter_grade || g.letter_grade || '—') as string}
										</span>
									</td>
									<td class="px-4 py-2.5 text-center text-xs">
										{#if g.is_finalized}
											<span class="text-emerald-600">Kesinleşti</span>
										{:else}
											<span class="text-amber-500">Taslak</span>
										{/if}
									</td>
									<td class="px-4 py-2.5 text-center">
										{#if !g.is_finalized}
											<button
												type="button"
												disabled={gradeDeletingId === g.enrollment_id}
												on:click={() => removeStudentGrade(g.enrollment_id)}
												class="text-xs font-semibold text-red-600 hover:underline disabled:opacity-50 dark:text-red-400"
											>
												{gradeDeletingId === g.enrollment_id ? '…' : 'Notu sil'}
											</button>
										{:else}
											<span class="text-xs text-slate-400">—</span>
										{/if}
									</td>
								</tr>
							{:else}
								<tr>
									<td colspan="7" class="px-4 py-8 text-center text-sm text-slate-400">
										Öğrenci bulunamadı.
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<div class="flex gap-2 border-t border-black/5 px-5 py-3 dark:border-white/10">
					<button
						on:click={saveGrades}
						disabled={gradeSaving}
						type="button"
						class="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
					>
						{gradeSaving ? 'Kaydediliyor…' : 'Kaydet'}
					</button>
					<button
						on:click={finalizeGrades}
						type="button"
						class="rounded-lg border border-emerald-200 px-4 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-50 dark:border-emerald-900/40 dark:text-emerald-400 transition-colors"
					>
						Kesinleştir
					</button>
				</div>
			</div>

			<!-- ============================================================ -->
			<!-- YOKLAMA GİRİŞİ                                               -->
			<!-- ============================================================ -->
		{:else if apiKey === 'attendance-entry'}
			<div class="flex flex-wrap items-center gap-4">
				<div class="flex items-center gap-2">
					<span class="text-xs font-semibold text-slate-500">Akademik dönem:</span>
					<select
						bind:value={selectedAttendanceTermId}
						on:change={() => {
							// Dönem değişti → şubeyi sıfırla, liste yeniden yüklensin
							selectedSection = '';
							sectionStudents = [];
							attendanceStatus = {};
							void loadPage();
						}}
						class="min-w-[12rem] rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5"
					>
						{#each termsSortedForSections as t}
							<option value={t.id}>
								{formatTermDropdownLabel(t)}{t.is_active ? ' (aktif)' : ''}
							</option>
						{/each}
					</select>
				</div>
				<div class="flex items-center gap-2">
					<span class="text-xs font-semibold text-slate-500">Şube:</span>
					<select
						bind:value={selectedSection}
						on:change={() => loadPage()}
						disabled={!sections.length}
						class="min-w-[10rem] rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none disabled:opacity-50 dark:border-white/10 dark:bg-white/5"
					>
						{#if !sections.length}
							<option value="">Bu dönemde şube yok</option>
						{/if}
						{#each sections as s}
							<option value={s.id}>
								{s.course_code}{s.section_no ? ` (Şube ${s.section_no})` : ''}
							</option>
						{/each}
					</select>
				</div>
				<div class="flex items-center gap-2">
					<span class="text-xs font-semibold text-slate-500">Hafta:</span>
					<select
						bind:value={weekNoUi}
						on:change={async () => {
							weekTouched = true;
							if (browser && selectedSection) {
								sessionStorage.setItem(attendanceWeekStorageKey(selectedSection), weekNoUi);
							}
							await loadAttendanceWeek();
						}}
						disabled={!selectedSection}
						class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none disabled:opacity-50 dark:border-white/10 dark:bg-white/5"
					>
						{#each Array.from({ length: weekCount }, (_, i) => i + 1) as w}
							<option value={String(w)}>{w}. hafta</option>
						{/each}
					</select>
					{#if attendanceLoadingWeek}
						<span class="text-xs text-slate-400">Yükleniyor…</span>
					{/if}
				</div>
			</div>
			{#if selectedSectionMeta}
				<div class="text-xs text-slate-500">
					<strong class="text-slate-700 dark:text-slate-200"
						>{selectedSectionMeta.course_code}</strong
					>
					— {selectedSectionMeta.course_name}
					{#if selectedSectionMeta.section_no}
						· Şube {selectedSectionMeta.section_no}
					{/if}
					{#if selectedSectionMeta.day_of_week}
						· {selectedSectionMeta.day_of_week} {selectedSectionMeta.start_time}
					{/if}
				</div>
			{/if}
			{#if attendanceSaved}
				<div
					class="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
				>
					Yoklama kaydedildi.
				</div>
			{/if}
			{#if attendanceErr}
				<div
					class="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
				>
					{attendanceErr}
				</div>
			{/if}
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="grid grid-cols-4 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
				>
					<div class="col-span-2">Öğrenci</div>
					<div>No</div>
					<div>Durum</div>
				</div>
				{#each sectionStudents as s}
					<div
						class="grid grid-cols-4 items-center border-t border-black/5 px-5 py-3 text-sm dark:border-white/10"
					>
						<div class="col-span-2 font-medium">{s.name}</div>
						<div class="font-mono text-xs text-slate-400">{s.student_no}</div>
						<div class="flex gap-2">
							{#each [['present', 'Var', 'emerald'], ['absent', 'Yok', 'red'], ['excused', 'Mazeret', 'amber']] as [val, label, color]}
								<button
									type="button"
									on:click={() =>
										(attendanceStatus[s.enrollment_id] = val as 'present' | 'absent' | 'excused')}
									class="rounded-lg px-2 py-1 text-xs font-medium transition-all
										{attendanceStatus[s.enrollment_id] === val
										? `bg-${color}-100 text-${color}-700 ring-1 ring-${color}-200 dark:bg-${color}-900/40 dark:text-${color}-300`
										: 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-white/10 dark:hover:bg-white/20'}"
								>
									{label}
								</button>
							{/each}
						</div>
					</div>
				{:else}
					<div class="px-5 py-8 text-center text-sm text-slate-400">Öğrenci yok.</div>
				{/each}
				{#if sectionStudents.length}
					<div class="border-t border-black/5 px-5 py-3 dark:border-white/10">
						<button
							on:click={saveAttendance}
							disabled={attendanceSaving}
							type="button"
							class="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors disabled:opacity-50"
						>
							{attendanceSaving ? 'Kaydediliyor…' : 'Yoklamayı Kaydet'}
						</button>
					</div>
				{/if}
			</div>

			<!-- ============================================================ -->
			<!-- SINAV TANIMLAMA                                              -->
			<!-- ============================================================ -->
		{:else if apiKey === 'exam-define'}
			<div class="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
				<label class="block min-w-[min(100%,14rem)]">
					<span class="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400"
						>Akademik dönem</span
					>
					<select
						bind:value={selectedExamsTermId}
						on:change={() => loadPage()}
						class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
					>
						{#if examsTermsActive.length}
							<optgroup label="Aktif dönem">
								{#each examsTermsActive as t}
									<option value={t.id}>{formatTermDropdownLabel(t)}</option>
								{/each}
							</optgroup>
						{/if}
						{#if examsTermsOther.length}
							<optgroup
								label={examsTermsActive.length ? 'Diğer dönemler' : 'Akademik dönemler'}
							>
								{#each examsTermsOther as t}
									<option value={t.id}>{formatTermDropdownLabel(t)}</option>
								{/each}
							</optgroup>
						{/if}
					</select>
				</label>
				<label class="block min-w-[min(100%,22rem)] flex-1">
					<span class="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400"
						>Ders / şube</span
					>
					<select
						bind:value={selectedSection}
						on:change={() => loadPage()}
						class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
					>
						{#each sections as s}
							<option value={s.id}>{formatSectionExamChoice(s)}</option>
						{/each}
					</select>
				</label>
			</div>
			{#if selectedSectionMeta}
				<div
					class="rounded-lg border border-sky-200/80 bg-sky-50/80 px-4 py-3 text-sm dark:border-sky-900/40 dark:bg-sky-950/25"
				>
					<div class="font-bold text-slate-800 dark:text-slate-100">
						{selectedSectionMeta.course_code}
						<span class="font-semibold text-slate-600 dark:text-slate-300"> — </span>
						{selectedSectionMeta.course_name}
					</div>
					<div class="mt-1 text-xs text-slate-600 dark:text-slate-400">
						Şube {selectedSectionMeta.section_code ?? '—'}
						{#if examDefineTermRow}
							<span class="text-slate-400"> · </span>
							{formatTermDropdownLabel(examDefineTermRow)}
						{/if}
						{#if selectedSectionMeta.day_of_week || selectedSectionMeta.start_time}
							<span class="text-slate-400"> · </span>
							{selectedSectionMeta.day_of_week}
							{selectedSectionMeta.start_time}{#if selectedSectionMeta.end_time}
								–{selectedSectionMeta.end_time}{/if}
						{/if}
					</div>
				</div>
			{/if}
			{#if !sections.length}
				<div
					class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100"
				>
					Bu dönem için atanmış şubeniz yok veya liste boş. Dönem seçimini veya OBS şube
					atamalarını kontrol edin.
				</div>
			{/if}
			{#if examClassroomsErr}
				<div
					class="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
				>
					<strong>Derslik listesi:</strong>
					{examClassroomsErr}
				</div>
			{/if}

			<!-- Mevcut sınavlar -->
			{#if exams.length}
				<div
					class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="border-b border-black/5 px-5 py-3 dark:border-white/10">
						<div class="text-xs font-bold uppercase tracking-wide text-slate-400">
							Tanımlı sınavlar
						</div>
						{#if selectedSectionMeta}
							<div class="mt-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
								{selectedSectionMeta.course_code} — {selectedSectionMeta.course_name}
								<span class="font-normal text-slate-500"> ({exams.length})</span>
							</div>
						{/if}
					</div>
					{#each exams as ex}
						<div
							class="border-t border-black/5 px-5 py-3 text-sm dark:border-white/10 {editingExamId === ex.id
								? 'bg-sky-50 dark:bg-sky-900/20'
								: ''}"
						>
							{#if editingExamId === ex.id}
								<div class="mb-3 text-xs font-bold text-sky-600 dark:text-sky-400">
									Sınavı düzenle
								</div>
								{#if examErr}
									<div
										class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
										role="alert"
									>
										{examErr}
									</div>
								{/if}
								<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Sınav Türü</div>
										<select
											bind:value={examEditForm.exam_type}
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
										>
											<option value="midterm">Vize</option>
											<option value="final">Final</option>
											<option value="makeup">Bütünleme</option>
											<option value="project">Proje</option>
										</select>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Tarih</div>
										<input
											type="date"
											bind:value={examEditForm.exam_date}
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
										/>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Saat</div>
										<input
											type="time"
											bind:value={examEditForm.exam_time}
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
										/>
									</label>
									<label class="block sm:col-span-2 lg:col-span-3">
										<div class="mb-1 text-xs font-semibold text-slate-500">Derslik</div>
										<select
											bind:value={examEditForm.classroom}
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
										>
											<option value="">Derslik seçilmedi</option>
											{#if examEditForm.classroom && !examClassrooms.some((c) => c.code === examEditForm.classroom)}
												<option value={examEditForm.classroom}
													>{examEditForm.classroom} (kayıtta)</option
												>
											{/if}
											{#each examClassrooms as cr}
												<option value={cr.code}>{cr.label ?? cr.code}</option>
											{/each}
										</select>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Ağırlık %</div>
										<input
											type="number"
											bind:value={examEditForm.weight_percent}
											min="0"
											max="100"
											step="0.5"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
										/>
									</label>
								</div>
								<div class="mt-3 flex flex-wrap gap-2">
									<button
										type="button"
										on:click={saveExamEdit}
										disabled={examEditSaving}
										class="rounded-lg bg-sky-500 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-400 disabled:opacity-50"
									>
										{examEditSaving ? 'Kaydediliyor…' : 'Kaydet'}
									</button>
									<button
										type="button"
										on:click={cancelExamEdit}
										disabled={examEditSaving}
										class="rounded-lg border border-black/10 bg-white px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"
									>
										İptal
									</button>
								</div>
							{:else}
								<div class="flex flex-wrap items-center justify-between gap-3">
									<div class="flex flex-wrap items-center gap-3">
										<span
											class="rounded-full px-2 py-0.5 text-xs font-medium
											{ex.exam_type === 'midterm'
												? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300'
												: ex.exam_type === 'final'
													? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
													: ex.exam_type === 'makeup'
														? 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300'
														: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'}"
										>
											{examTypeLabel(ex.exam_type)}
										</span>
										<span>{ex.exam_date} {ex.exam_time}</span>
										<span class="text-xs text-slate-400">{ex.classroom || '—'}</span>
										<span class="text-xs font-semibold text-slate-500"
											>%{Number(ex.weight_percent ?? 0)}</span
										>
									</div>
									<div class="flex items-center gap-2">
										<button
											type="button"
											on:click={() => openExamEdit(ex)}
											disabled={!!deletingExamId || examEditSaving}
											class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
										>
											Düzenle
										</button>
										<button
											type="button"
											on:click={() => removeExam(ex)}
											disabled={deletingExamId === ex.id || !!editingExamId}
											class="rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-900/50 dark:bg-white/5 dark:text-red-400 dark:hover:bg-red-950/30"
										>
											{deletingExamId === ex.id ? 'Siliniyor…' : 'Sil'}
										</button>
									</div>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{:else if sections.length && selectedSection}
				<div
					class="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-5 py-8 text-center text-sm text-slate-500 dark:border-white/15 dark:bg-white/5 dark:text-slate-400"
				>
					<p class="font-medium text-slate-600 dark:text-slate-300">
						Bu şube için henüz sınav kaydı yok.
					</p>
					<p class="mt-2 text-xs">
						Aşağıdaki formdan sınav ekleyebilir; sonra listeden <strong>Düzenle</strong> veya
						<strong>Sil</strong> ile güncelleyebilirsiniz.
					</p>
				</div>
			{/if}

			<!-- Yeni sınav formu -->
			<div
				class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5 {!sections.length ||
				!selectedSection
					? 'opacity-60'
					: ''}"
			>
				<div class="mb-4 font-semibold">Yeni Sınav Tanımla</div>
				{#if examSaved}
					<div
						class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
					>
						Sınav eklendi.
					</div>
				{/if}
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Sınav Türü</div>
						<select
							bind:value={examForm.exam_type}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						>
							<option value="midterm">Vize</option>
							<option value="final">Final</option>
							<option value="makeup">Bütünleme</option>
							<option value="project">Proje</option>
						</select>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Tarih</div>
						<input
							type="date"
							bind:value={examForm.exam_date}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						/>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Saat</div>
						<input
							type="time"
							bind:value={examForm.exam_time}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						/>
					</label>
					<label class="block sm:col-span-2">
						<div class="mb-1 text-xs font-semibold text-slate-500">Derslik</div>
						<select
							bind:value={examForm.classroom}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						>
							<option value="">Derslik seçilmedi</option>
							{#each examClassrooms as cr}
								<option value={cr.code}>{cr.label ?? cr.code}</option>
							{/each}
						</select>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Ağırlık %</div>
						<input
							type="number"
							bind:value={examForm.weight_percent}
							min="0"
							max="100"
							step="0.5"
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						/>
					</label>
				</div>
				{#if examErr && !editingExamId}
					<div
						class="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-300"
						role="alert"
					>
						{examErr}
					</div>
				{/if}
				<button
					on:click={createExam}
					disabled={examSaving || !sections.length || !selectedSection}
					type="button"
					class="{examErr && !editingExamId ? 'mt-3' : 'mt-4'} rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
				>
					{examSaving ? 'Ekleniyor…' : 'Sınav Ekle'}
				</button>
			</div>

			<!-- ============================================================ -->
			<!-- DANIŞMANLIK ÖĞRENCİLERİM                                    -->
			<!-- ============================================================ -->
		{:else if apiKey === 'advisees'}
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="grid grid-cols-6 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
				>
					<div class="col-span-2">Ad Soyad</div>
					<div>No</div>
					<div>GNO</div>
					<div>Sınıf</div>
					<div class="text-right">Kayıt</div>
				</div>
				{#each advisees as a}
					{@const adv = a as {
						student_user_id?: string;
						name: string;
						student_no: string;
						gpa: number;
						class_level: number;
						status: string;
					}}
					<div
						class="grid grid-cols-6 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10 hover:bg-slate-50/50 transition-colors"
					>
						<div class="col-span-2 font-medium">{adv.name}</div>
						<div class="font-mono text-xs text-slate-400">{adv.student_no}</div>
						<div class="font-bold {adviseeGpaTextClass(adv.gpa)}">
							{adv.gpa.toFixed(2)}
						</div>
						<div class="text-slate-500">{adv.class_level}. Sınıf</div>
						<div class="text-right">
							<button
								type="button"
								on:click={() => loadAdviseeEnrollments(adv.student_user_id ?? '')}
								class="rounded-lg bg-sky-500 px-2.5 py-1 text-xs font-semibold text-white hover:bg-sky-400"
							>
								Ders yükü
							</button>
						</div>
					</div>
				{:else}
					<div class="px-5 py-8 text-center text-sm text-slate-400">Danışman öğrencisi yok.</div>
				{/each}
			</div>

			{#if adviseeDetailUserId}
				<div
					class="mt-4 space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-5 dark:border-indigo-900/40 dark:bg-indigo-950/20"
				>
					<div class="flex flex-wrap items-center justify-between gap-2">
						<span class="text-sm font-bold text-indigo-900 dark:text-indigo-100">
							Öğrencinin ders yükü — kullanıcı:
							<span class="font-mono text-xs">{adviseeDetailUserId}</span>
						</span>
						<button
							type="button"
							on:click={() => {
								adviseeDetailUserId = null;
								adviseeEnrollments = [];
							}}
							class="text-xs text-indigo-600 hover:underline"
						>
							Kapat
						</button>
					</div>
					{#if adviseeSchedErr}
						<div class="rounded-lg bg-red-100 px-3 py-2 text-sm text-red-800">{adviseeSchedErr}</div>
					{/if}
					{#if adviseeSchedBusy}
						<div class="text-sm text-slate-500">Yükleniyor…</div>
					{:else if adviseeEnrollments.length}
						<div class="overflow-x-auto rounded-lg border border-indigo-100 bg-white dark:border-indigo-900/30 dark:bg-white/5">
							<table class="w-full text-sm">
								<thead class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5">
									<tr>
										<th class="px-3 py-2 text-left">Kod</th>
										<th class="px-3 py-2 text-left">Ders</th>
										<th class="px-3 py-2 text-center">AKTS</th>
										<th class="px-3 py-2 text-left">DB durumu</th>
									</tr>
								</thead>
								<tbody>
									{#each adviseeEnrollments as e}
										<tr class="border-t border-black/5 dark:border-white/10">
											<td class="px-3 py-2 font-mono text-xs">{e.course_code}</td>
											<td class="px-3 py-2">{e.course_name}</td>
											<td class="px-3 py-2 text-center">{e.akts}</td>
											<td class="px-3 py-2">
												{#if e.status === 'draft'}
													<span class="text-slate-500">taslak</span>
												{:else if e.status === 'pending'}
													<span class="font-semibold text-amber-700 dark:text-amber-300">
														danışmanda
													</span>
												{:else if e.status === 'active'}
													<span class="font-semibold text-emerald-700 dark:text-emerald-300">
														kesinleştirildi (obs_course_enrollments.active)
													</span>
												{:else}
													{e.status}
												{/if}
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
						<div class="flex flex-wrap gap-2">
							<button
								type="button"
								disabled={adviseeSchedBusy}
								on:click={() => adviseeDetailUserId && runFinalizeSched(adviseeDetailUserId)}
								class="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50"
							>
								Kesinleştir (onaylanmış ders değişiklik talebi → kayıt)
							</button>
							<button
								type="button"
								disabled={adviseeSchedBusy}
								on:click={() => adviseeDetailUserId && runRejectSched(adviseeDetailUserId)}
								class="rounded-lg border border-red-300 bg-white px-4 py-2 text-xs font-bold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:bg-transparent"
							>
								Listeyi iade et (pending → taslak)
							</button>
						</div>
						<p class="text-xs text-indigo-800/80 dark:text-indigo-200/80">
							Aynı işlem <strong>Onay Talepleri</strong> sayfasındaki talepler için <strong>Onayla</strong> veya
							<strong>Reddet</strong> ile de yapılabilir; kayıtlar <code>obs_approval_requests</code> ve
							<code>obs_course_enrollments</code> üzerinden güncellenir.
						</p>
					{/if}
				</div>
			{/if}

			<!-- ============================================================ -->
			<!-- ONAY TALEPLERİ                                               -->
			<!-- ============================================================ -->
		{:else if apiKey === 'approvals'}
			<div class="space-y-3">
				{#if approvalErr}
					<div
						class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
					>
						{approvalErr}
					</div>
				{/if}
				{#each approvals as req}
					<div
						class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
					>
						<div class="flex items-start justify-between gap-4">
							<div class="min-w-0 flex-1">
								<div class="text-sm font-bold text-slate-800 dark:text-slate-100">
									{#if req.add_drop_detail}
										Öğrencinin ders değişiklik talebi
									{:else if req.request_type === 'schedule_batch'}
										Ders kayıt / değişiklik talebi
									{:else}
										{req.request_type}
									{/if}
								</div>
								<div class="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-200">
									{req.add_drop_detail?.student_name ?? req.student_name ?? 'Öğrenci'}
									<span class="ml-2 font-mono text-xs font-normal text-slate-500"
										>{req.add_drop_detail?.student_no ?? req.student_no}</span
									>
								</div>
								{#if req.add_drop_detail}
									<div class="mt-1 text-xs text-slate-500">
										{req.add_drop_detail.department_name} · Dönem:
										{req.add_drop_detail.term_name || req.add_drop_detail.term_id}
									</div>
									<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
										<span
											><span class="font-semibold text-slate-800 dark:text-slate-200"
												>Planlanan AKTS:</span
											>
											{req.add_drop_detail.projected_akts}</span
										>
										<span
											><span class="font-semibold text-slate-800 dark:text-slate-200">GNO:</span>
											{req.add_drop_detail.agno != null
												? req.add_drop_detail.agno.toFixed(2)
												: '—'}</span
										>
										<span
											><span class="font-semibold text-slate-800 dark:text-slate-200"
												>İzin verilen aralık:</span
											>
											{req.add_drop_detail.akts_min}–{req.add_drop_detail.akts_max} AKTS</span
										>
									</div>
								{/if}
								<div class="mt-1 text-xs text-slate-400">
									{req.request_type === 'schedule_batch' && req.add_drop_detail
										? 'Ders ekle-bırak (danışman onayı)'
										: req.request_type === 'schedule_batch'
											? 'Ders kayıt (danışman onayı)'
											: req.request_type} · {req.created_at?.slice(0, 10)}
								</div>
								{#if req.note}
									<div class="mt-2 whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">
										{req.note}
									</div>
								{/if}
								{#if req.add_drop_detail}
									<div
										class="mt-4 grid gap-4 rounded-lg border border-slate-100 bg-slate-50/60 p-4 text-sm dark:border-white/10 dark:bg-white/5"
									>
										<div>
											<div
												class="mb-1 text-[11px] font-bold uppercase tracking-wide text-emerald-800 dark:text-emerald-200"
											>
												Eklenen dersler
											</div>
											<ul class="list-inside list-disc text-slate-700 dark:text-slate-300">
												{#each req.add_drop_detail.added_courses as c}
													<li>{c.course_code} — {c.course_name} ({c.akts} AKTS)</li>
												{:else}
													<li class="list-none text-slate-400">—</li>
												{/each}
											</ul>
										</div>
										<div>
											<div
												class="mb-1 text-[11px] font-bold uppercase tracking-wide text-amber-800 dark:text-amber-200"
											>
												Bırakılacak dersler
											</div>
											<ul class="list-inside list-disc text-slate-700 dark:text-slate-300">
												{#each req.add_drop_detail.dropped_courses as c}
													<li>{c.course_code} — {c.course_name} ({c.akts} AKTS)</li>
												{:else}
													<li class="list-none text-slate-400">—</li>
												{/each}
											</ul>
										</div>
										<div>
											<div
												class="mb-1 text-[11px] font-bold uppercase tracking-wide text-slate-600 dark:text-slate-400"
											>
												Mevcut (korunan) dersler
											</div>
											<ul class="list-inside list-disc text-slate-700 dark:text-slate-300">
												{#each req.add_drop_detail.kept_courses as c}
													<li>{c.course_code} — {c.course_name} ({c.akts} AKTS)</li>
												{:else}
													<li class="list-none text-slate-400">—</li>
												{/each}
											</ul>
										</div>
									</div>
								{/if}
							</div>
							{#if req.status === 'pending'}
								<div class="flex shrink-0 gap-2">
									<button
										on:click={() => resolveApproval(req.id, 'approve')}
										type="button"
										class="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-400 transition-colors"
									>
										Onayla
									</button>
									<button
										on:click={() => resolveApproval(req.id, 'reject')}
										type="button"
										class="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50 dark:border-red-900/40 dark:hover:bg-red-950/20 transition-colors"
									>
										Reddet
									</button>
								</div>
							{:else}
								<span
									class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold
									{req.status === 'approved'
										? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
										: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}"
								>
									{req.status === 'approved' ? 'Onaylandı' : 'Reddedildi'}
								</span>
							{/if}
						</div>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400"
					>
						Bekleyen onay talebi yok.
					</div>
				{/each}
			</div>

			<!-- ============================================================ -->
			<!-- DUYURU OLUŞTUR                                               -->
			<!-- ============================================================ -->
		{:else if apiKey === 'announce'}
			<div class="mx-auto max-w-3xl space-y-6">
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
						<svg
							class="h-4 w-4 text-sky-500"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path
								d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"
							/>
						</svg>
						{editingAnnId ? 'Duyuru Düzenle' : 'Duyuru Oluştur'}
					</div>
					{#if annSaved}
						<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Duyuru kaydedildi.
						</div>
					{/if}
					{#if annErr}
						<div
							class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400"
						>
							{annErr}
						</div>
					{/if}
					<div class="space-y-3">
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">Başlık</div>
							<input
								bind:value={annForm.title}
								maxlength={255}
								placeholder="Duyuru başlığı…"
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
							/>
						</label>
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">İçerik</div>
							<textarea
								bind:value={annForm.content}
								maxlength={255}
								rows="5"
								placeholder="Duyuru içeriği…"
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
							></textarea>
						</label>

						<div>
							<div class="mb-1.5 text-xs font-semibold text-slate-500">Hedef Kitle</div>
							<div class="grid grid-cols-2 gap-2">
								{#each [{ v: 'section', lbl: 'Şubedeki Öğrenciler' }, { v: 'advisees', lbl: 'Danışmanlık Öğrencilerim' }, { v: 'student', lbl: 'Belirli Bir Öğrenci' }, { v: 'all', lbl: 'Tüm Öğrenciler' }] as opt}
									<button
										type="button"
										on:click={() => {
											annForm.audience_type = opt.v as typeof annForm.audience_type;
										}}
										class="flex w-full items-center justify-center rounded-lg border px-3 py-2.5 text-xs font-medium transition-colors
										{annForm.audience_type === opt.v
											? 'border-sky-400 bg-sky-50 text-sky-700 dark:border-sky-500 dark:bg-sky-900/30 dark:text-sky-300'
											: 'border-black/10 bg-white text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10'}"
									>
										{opt.lbl}
									</button>
								{/each}
							</div>
						</div>

						{#if annForm.audience_type === 'section'}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Şube Seç</div>
								<select
									bind:value={annForm.section_id}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
								>
									<option value="">— Şube seçin —</option>
									{#each sections as s}
										<option value={s.id}>{s.course_code} — {s.course_name} ({s.day_of_week})</option>
									{/each}
								</select>
							</label>
						{/if}

						{#if annForm.audience_type === 'student'}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Öğrenci No</div>
								<input
									bind:value={annForm.student_no}
									placeholder="Örn: 20240001"
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
								/>
							</label>
						{/if}

						{#if editingAnnId}
							<label
								class="flex cursor-pointer items-center gap-2 text-sm text-slate-600 dark:text-slate-300"
							>
								<input type="checkbox" bind:checked={annIsActive} class="rounded border-black/20" />
								Aktif (yayında görünsün)
							</label>
						{/if}

						<div class="flex flex-col gap-2 sm:flex-row sm:items-stretch">
							{#if editingAnnId}
								<button
									type="button"
									on:click={cancelEditAnn}
									class="w-full rounded-lg border border-black/10 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10 sm:w-auto sm:px-6"
								>
									İptal
								</button>
							{/if}
							<button
								on:click={async () => {
									const t = annForm.title.trim();
									const c = annForm.content.trim();
									const maxLen = 255;
									if (!t || !c) {
										annErr = 'Başlık ve içerik zorunlu.';
										return;
									}
									if (t.length > maxLen || c.length > maxLen) {
										annErr = `Başlık ve içerik en fazla ${maxLen} karakter olabilir.`;
										return;
									}
									if (annForm.audience_type === 'section' && !annForm.section_id?.trim()) {
										annErr = 'Şube seçmelisiniz.';
										return;
									}
									if (annForm.audience_type === 'student' && !annForm.student_no?.trim()) {
										annErr = 'Öğrenci numarası girin.';
										return;
									}
									annSaving = true;
									annErr = null;
									const token = localStorage.token ?? null;
									try {
										if (editingAnnId) {
											await updateDouAcademicAnnouncement(token, editingAnnId, {
												title: t,
												content: c,
												audience_type: annForm.audience_type,
												course_section_id:
													annForm.audience_type === 'section'
														? annForm.section_id.trim()
														: null,
												student_no:
													annForm.audience_type === 'student'
														? annForm.student_no.trim()
														: null,
												is_active: annIsActive
											});
										} else {
											const body: AcademicAnnouncementBody = {
												title: t,
												content: c,
												audience_type: annForm.audience_type,
												course_section_id:
													annForm.audience_type === 'section'
														? annForm.section_id.trim()
														: undefined,
												student_no:
													annForm.audience_type === 'student'
														? annForm.student_no.trim()
														: undefined
											};
											await createDouAcademicAnnouncement(token, body);
										}
										annSaved = true;
										cancelEditAnn();
										const refreshed = await getDouAcademicAnnouncements(token);
										myAnnouncements = refreshed.announcements ?? [];
										setTimeout(() => (annSaved = false), 4000);
									} catch (e: unknown) {
										annErr = e instanceof Error ? e.message : 'İşlem başarısız.';
									} finally {
										annSaving = false;
									}
								}}
								disabled={annSaving}
								type="button"
								class="w-full rounded-lg bg-sky-500 py-2.5 text-sm font-bold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors sm:flex-1"
							>
								{annSaving ? 'Gönderiliyor…' : editingAnnId ? 'Kaydet' : 'Duyuruyu Yayınla'}
							</button>
						</div>
					</div>
				</div>

				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-3 font-semibold text-slate-800 dark:text-slate-100">Duyurularım</div>
					{#each myAnnouncements as a}
						<div
							class="mb-3 rounded-lg border border-black/5 bg-slate-50/80 p-4 last:mb-0 dark:border-white/10 dark:bg-white/5"
						>
							<div class="flex flex-wrap items-start justify-between gap-2">
								<div class="min-w-0 font-medium text-sm text-slate-800 dark:text-slate-100">
									{a.title}
								</div>
								<div class="flex shrink-0 gap-1">
									<button
										type="button"
										on:click={() => startEditAnn(a)}
										class="rounded-lg border border-black/10 px-2.5 py-1 text-xs font-semibold text-sky-600 hover:bg-sky-50 dark:border-white/10 dark:text-sky-400 dark:hover:bg-sky-950/30"
									>
										Düzenle
									</button>
									<button
										type="button"
										on:click={() => removeAnn(a.id)}
										class="rounded-lg border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 dark:border-red-900/40 dark:text-red-400 dark:hover:bg-red-950/20"
									>
										Sil
									</button>
								</div>
							</div>
							<div class="mt-1 text-xs text-slate-400">
								{a.audience_type}
								{#if !a.is_active}
									<span class="text-amber-600 dark:text-amber-400"> · pasif</span>
								{/if}
								{#if a.created_at}
									{' · '}{a.created_at.slice(0, 16).replace('T', ' ')}
								{/if}
							</div>
							<p class="mt-2 line-clamp-2 text-sm text-slate-600 dark:text-slate-300">{a.content}</p>
						</div>
					{:else}
						<div class="py-8 text-center text-sm text-slate-400">Henüz duyuru yok.</div>
					{/each}
				</div>
			</div>

			<!-- ============================================================ -->
			<!-- MESAJLAR                                                      -->
			<!-- ============================================================ -->
		{:else if apiKey === 'inbox' || apiKey === 'sent'}
			{@const msgs =
				apiKey === 'inbox'
					? inboxMsgs.filter((m) => m.status !== 'deleted')
					: sentMsgs.filter((m) => m.status !== 'deleted')}
			<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
				<span class="text-xs text-slate-400">{msgs.length} mesaj</span>
				<button
					type="button"
					on:click={openAcademicNewMessage}
					class="flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-400"
				>
					Yeni Mesaj
				</button>
			</div>
			<p class="mb-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
				Danışmanlık öğrencilerinize veya ders verdiğiniz şubedeki öğrenciye yazabilirsiniz. Gelen
				mesajlarda <span class="font-medium text-slate-600 dark:text-slate-300">Cevapla</span> ile
				gönderene dönün.
			</p>
			<div class="space-y-2">
				{#each msgs as m}
					<div
						class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0 font-semibold text-sm">{m.subject}</div>
							{#if apiKey === 'inbox' && m.sender_user_id}
								<button
									type="button"
									on:click={() => openAcademicReply(m)}
									class="shrink-0 rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-700 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300 dark:hover:bg-sky-900/30"
								>
									Cevapla
								</button>
							{/if}
						</div>
						<div class="mt-1 text-xs text-slate-400">
							{apiKey === 'inbox'
								? (m.sender_name ?? m.sender_type)
								: `Alıcı: ${m.receiver_name ?? m.receiver_type}`} · {m.sent_at}
						</div>
						<p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{m.body}</p>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400"
					>
						{apiKey === 'inbox' ? 'Gelen kutunuz boş.' : 'Gönderilen mesaj yok.'}
					</div>
				{/each}
			</div>

			{#if showAcademicCompose}
				<div
					class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
				>
					<div
						class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-black/10 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-slate-900"
					>
						<div class="mb-5 flex items-center justify-between">
							<div class="font-bold text-slate-800 dark:text-slate-100">
								{academicComposeReplyTo ? 'Cevap yaz' : 'Yeni Mesaj'}
							</div>
							<button
								type="button"
								on:click={() => {
									showAcademicCompose = false;
									resetAcademicCompose();
								}}
								class="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200">✕</button
							>
						</div>
						{#if academicComposeErr}
							<div
								class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
							>
								{academicComposeErr}
							</div>
						{/if}
						<div class="space-y-3">
							{#if academicComposeReplyTo}
								<div class="rounded-xl border border-sky-200 bg-sky-50/80 px-3.5 py-2.5 text-sm dark:border-sky-900/50 dark:bg-sky-950/20">
									<div class="text-xs font-semibold text-slate-500">Alıcı</div>
									<div class="font-medium text-slate-800 dark:text-slate-100">
										{academicComposeReplyTo.displayName}
									</div>
								</div>
							{:else}
								<div class="flex gap-2 rounded-xl border border-black/10 p-1 dark:border-white/10">
									<button
										type="button"
										on:click={() => {
											academicComposeRecipientMode = 'advisee';
											academicComposeSectionStudentUid = '';
										}}
										class="flex-1 rounded-lg py-2 text-xs font-semibold transition-colors {academicComposeRecipientMode ===
										'advisee'
											? 'bg-sky-500 text-white'
											: 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10'}"
									>
										Danışmanlık
									</button>
									<button
										type="button"
										on:click={() => {
											academicComposeRecipientMode = 'section';
											academicComposeAdviseeId = '';
										}}
										class="flex-1 rounded-lg py-2 text-xs font-semibold transition-colors {academicComposeRecipientMode ===
										'section'
											? 'bg-sky-500 text-white'
											: 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10'}"
									>
										Şube öğrencisi
									</button>
								</div>
								{#if academicComposeRecipientMode === 'advisee'}
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Öğrenci</div>
										<select
											bind:value={academicComposeAdviseeId}
											class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
										>
											<option value="">Seçin…</option>
											{#each msgAdvisees as a}
												<option value={a.student_user_id}>
													{a.name}
													{a.student_no ? ` (${a.student_no})` : ''}
												</option>
											{/each}
										</select>
										{#if !msgAdvisees.length}
											<p class="mt-1 text-xs text-amber-600 dark:text-amber-400">
												Danışmanlık öğrencisi yok; şube sekmesinden veya gelen mesajdan cevap
												verin.
											</p>
										{/if}
									</label>
								{:else}
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Şube</div>
										<select
											bind:value={academicComposeSectionId}
											on:change={onAcademicComposeSectionChange}
											class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
										>
											<option value="">Şube seçin…</option>
											{#each sections as sec}
												<option value={sec.id}>
													{sec.course_code}
													{sec.course_name ? ` — ${sec.course_name}` : ''} ({sec.section_code})
												</option>
											{/each}
										</select>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Öğrenci</div>
										<select
											bind:value={academicComposeSectionStudentUid}
											disabled={!academicComposeSectionId || !academicComposeSectionStudents.length}
											class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 disabled:opacity-50 dark:border-white/10 dark:bg-slate-800"
										>
											<option value="">Öğrenci seçin…</option>
											{#each academicComposeSectionStudents.filter((s) => s.student_user_id) as st}
												<option value={st.student_user_id}>
													{st.name}{st.student_no ? ` (${st.student_no})` : ''}
												</option>
											{/each}
										</select>
									</label>
								{/if}
							{/if}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Konu</div>
								<input
									bind:value={academicComposeSubject}
									placeholder="Konu"
									class="w-full rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
								/>
							</label>
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Mesaj</div>
								<textarea
									bind:value={academicComposeBody}
									rows="6"
									placeholder="Mesajınız…"
									class="w-full resize-none rounded-xl border border-black/10 bg-white px-3.5 py-2.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/30 dark:border-white/10 dark:bg-slate-800"
								></textarea>
							</label>
							<div class="flex gap-2 pt-1">
								<button
									type="button"
									on:click={sendAcademicMessage}
									disabled={academicComposeSending ||
										!academicComposeSubject.trim() ||
										!academicComposeBody.trim()}
									class="flex-1 rounded-xl bg-sky-500 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-sky-400 disabled:opacity-50"
								>
									{academicComposeSending ? 'Gönderiliyor…' : 'Gönder'}
								</button>
								<button
									type="button"
									on:click={() => {
										showAcademicCompose = false;
										resetAcademicCompose();
									}}
									class="rounded-xl border border-black/10 px-4 py-2.5 text-sm transition-colors hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
								>
									İptal
								</button>
							</div>
						</div>
					</div>
				</div>
			{/if}

			<!-- ============================================================ -->
			<!-- ŞİFRE DEĞİŞTİR                                               -->
			<!-- ============================================================ -->
		{:else if apiKey === 'change-pw'}
			<div
				class="mx-auto max-w-md rounded-xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="mb-5 font-bold">Şifre Değiştir</div>
				{#if pwOk}
					<div
						class="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
					>
						{pwOk}
					</div>
				{/if}
				{#if pwErr}
					<div
						class="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300"
					>
						{pwErr}
					</div>
				{/if}
				<div class="space-y-4">
					{#each [['Mevcut Şifre', 'current_password'], ['Yeni Şifre', 'new_password'], ['Yeni Şifre (Tekrar)', 'confirm_password']] as [lbl, field]}
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">{lbl}</div>
							<input
								bind:value={pwForm[field as keyof typeof pwForm]}
								type="password"
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
								autocomplete="off"
							/>
						</label>
					{/each}
					<button
						on:click={changePassword}
						disabled={pwBusy}
						type="button"
						class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
					>
						{pwBusy ? '…' : 'Şifreyi Güncelle'}
					</button>
				</div>
			</div>
		{:else}
			<div
				class="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 p-8 text-center dark:border-white/10 dark:bg-white/5"
			>
				<div class="font-semibold text-slate-500">{pageTitle}</div>
				<p class="mt-1 text-sm text-slate-400">Sayfa bulunamadı.</p>
			</div>
		{/if}
	</div>
</ObsShell>
