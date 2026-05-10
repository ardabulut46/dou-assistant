<script lang="ts">
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { tick } from 'svelte';
	import { user } from '$lib/stores';
	import type { OgrenciPageMeta, OgrenciPath } from '$lib/obs/ogrenci/paths';

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
		type AvailableCourse
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
	let advisor: DouAdvisorResponse | null = null;
	let enrollments: DouEnrollment[] = [];
	let totalAkts = 0;
	let grades: DouGradeEntry[] = [];
	let gpaTerms: unknown[] = [];
	let cumulativeGpa: number | null = null;
	let transcript: unknown[] | null = null;
	let transcriptTotalAkts: number | null = null;
	let attendance: DouAttendanceRow[] = [];
	let exams: DouExam[] = [];
	let schedule: DouScheduleRow[] = [];
	let announcements: DouAnnouncement[] = [];
	let inboxMsgs: DouMessage[] = [];
	let sentMsgs: DouMessage[] = [];
	let docRequests: DouDocumentRequest[] = [];
	let availableCourses: AvailableCourse[] = [];
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

	// Ders Kayıt — taslaklar obs_course_enrollments (status=draft)
	let enrollSubmitting = false;
	let enrollSuccess: string | null = null;
	let enrollError: string | null = null;
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
	$: addDropProjectedAkts = enrollments.reduce((s, e) => {
		if (e.status === 'active' && !markedDrop.has(e.id)) return s + (e.akts || 0);
		if (e.status === 'draft' && (e.enrollment_reason || '') === 'add_drop')
			return s + (e.akts || 0);
		return s;
	}, 0);
	$: addDropAktsOk =
		addDropProjectedAkts >= addDropAktsMin && addDropProjectedAkts <= addDropAktsMax;
	$: addDropAktsRuleHint = (() => {
		const g =
			registrationLimits?.gpa_computed ??
			registrationLimits?.gpa ??
			registrationLimits?.gpa_profile;
		const gtxt = g != null ? g.toFixed(2) : '—';
		return `Ders ekle-bırak: planlanan dönem yükü ${addDropProjectedAkts} AKTS (zorunlu aralık ${addDropAktsMin}–${addDropAktsMax} AKTS). GNO: ${gtxt}.`;
	})();

	// Ders Ekle/Bırak — bırakılacaklar + taslaklar tek pakette danışmana
	let markedDrop: Set<string> = new Set();
	let dropSubmitting = false;
	let dropSuccess: string | null = null;
	let dropError: string | null = null;
	let addDropTermLabel = '—';

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
			if (apiKey === 'terms') terms = await getDouTerms(token).catch(() => []);
			if (apiKey === 'advisor') advisor = await getDouStudentAdvisor(token).catch(() => null);
			if (apiKey === 'enrollments') {
				const r = await getDouStudentEnrollments(token).catch(() => null);
				enrollments = r?.enrollments ?? [];
				totalAkts = r?.total_akts ?? 0;
			}
			if (apiKey === 'ders-ekle') {
				const [enrRes, avRes, termsRes] = await Promise.allSettled([
					getDouStudentEnrollments(token, undefined, 'active,draft,pending,pending_drop'),
					getDouAvailableCourses(token),
					getDouTerms(token)
				]);
				if (enrRes.status === 'fulfilled') {
					enrollments = enrRes.value.enrollments;
					totalAkts = enrRes.value.total_akts ?? 0;
				} else {
					enrollments = [];
					totalAkts = 0;
				}
				if (avRes.status === 'fulfilled') {
					availableCourses = avRes.value.sections ?? [];
				} else {
					availableCourses = [];
				}
				if (termsRes.status === 'fulfilled') {
					const tl = termsRes.value;
					const at = tl.find((t) => t.is_active) ?? tl[tl.length - 1];
					addDropTermLabel = at?.name ?? '—';
				} else {
					addDropTermLabel = '—';
				}
				{
					const limTid = enrollments.find((e) => e.term_id)?.term_id;
					registrationLimits = await getDouStudentRegistrationLimits(token, limTid).catch(() => null);
				}
			}
			if (apiKey === 'ders-kayit') {
				const [enrRes, avRes, termsRes] = await Promise.allSettled([
					getDouStudentEnrollments(token, undefined, 'draft,pending,active'),
					getDouAvailableCourses(token),
					getDouTerms(token)
				]);
				if (enrRes.status === 'fulfilled') {
					enrollments = enrRes.value.enrollments;
					totalAkts = enrRes.value.total_akts ?? 0;
				} else {
					enrollments = [];
					totalAkts = 0;
				}
				if (avRes.status === 'fulfilled') {
					availableCourses = avRes.value.sections ?? [];
				} else {
					availableCourses = [];
				}
				if (termsRes.status === 'fulfilled') {
					const tl = termsRes.value;
					const at = tl.find((t) => t.is_active) ?? tl[tl.length - 1];
					enrollmentTermLabel = at?.name ?? '—';
				} else {
					enrollmentTermLabel = '—';
				}
				{
					const limTid = enrollments.find((e) => e.term_id)?.term_id;
					registrationLimits = await getDouStudentRegistrationLimits(token, limTid).catch(() => null);
				}
			}
			if (apiKey === 'grades') {
				const r = await getDouStudentGrades(token).catch(() => null);
				grades = r?.grades ?? [];
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
				const r = await getDouStudentAttendance(token).catch(() => null);
				attendance = r?.attendance ?? [];
			}
			if (apiKey === 'exams') {
				const r = await getDouStudentExams(token).catch(() => null);
				exams = r?.exams ?? [];
			}
			if (apiKey === 'schedule') {
				const r = await getDouStudentSchedule(token).catch(() => null);
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
			class="flex items-center justify-between rounded-xl border border-black/10 bg-white px-5 py-3.5 shadow-sm dark:border-white/10 dark:bg-white/5"
		>
			<div>
				<h1 class="text-base font-bold text-slate-800 dark:text-slate-100">{pageTitle}</h1>
				<p class="mt-0.5 text-[11px] text-slate-400">{activePath}</p>
			</div>
		</div>

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
							<code class="rounded bg-amber-100/80 px-1 dark:bg-white/10">obs_student_profiles</code>
							tablosunda satırınız yok. <strong>OBS Yönetim → Kullanıcı Yönetimi</strong>’nde hesabınız
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
						<div class="flex items-start justify-between pt-10">
							<div>
								<div class="text-xl font-bold text-slate-900 dark:text-slate-100">
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
								class="mt-1 flex items-center gap-1.5 rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10 transition-colors"
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
							<div class="mt-5 grid grid-cols-4 gap-3">
								{#each [{ lbl: 'AGNO', val: agno.toFixed(2), sub: 'Kümülatif', color: agno >= 3.0 ? 'text-emerald-600 dark:text-emerald-400' : agno >= 2.0 ? 'text-sky-600 dark:text-sky-400' : 'text-red-500' }, { lbl: 'DNO', val: dno.toFixed(2), sub: 'Bu Dönem', color: dno >= 3.0 ? 'text-emerald-600 dark:text-emerald-400' : dno >= 2.0 ? 'text-sky-600 dark:text-sky-400' : 'text-red-500' }, { lbl: 'AKTS', val: tamamAkts.toString(), sub: `/ ${toplamAkts}`, color: 'text-slate-800 dark:text-slate-100' }, { lbl: 'Durum', val: profile.status === 'active' ? 'Aktif' : (profile.status ?? 'Aktif'), sub: profile.is_financially_eligible ? '✓ Mali Uygun' : '✗ Borç Var', color: profile.status === 'active' ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500' }] as st}
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
										class="mt-0.5 truncate text-sm font-medium text-slate-800 dark:text-slate-100"
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
								✓ Profil güncellendi.
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
					Kayıt <code class="rounded bg-slate-100 px-1 dark:bg-white/10">obs_student_profiles</code>
					tablosunda yoksa yönetimden profil oluşturulmalıdır.
				</p>
			</div>

			<!-- ================================================================ -->
			<!-- AKADEMİK TAKVİM                                                  -->
			<!-- ================================================================ -->
		{:else if apiKey === 'terms' && terms.length}
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="grid grid-cols-5 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
				>
					<div class="col-span-2">Dönem</div>
					<div>Yıl</div>
					<div>Başlangıç</div>
					<div>Bitiş</div>
				</div>
				{#each terms as t}
					<div
						class="grid grid-cols-5 border-t border-black/5 px-5 py-3.5 text-sm dark:border-white/10 {t.is_active
							? 'bg-sky-50/40 dark:bg-sky-900/10'
							: ''}"
					>
						<div class="col-span-2 font-medium">
							{t.name}
							{#if t.is_active}<span
									class="ml-2 rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
									>Aktif</span
								>{/if}
						</div>
						<div class="text-slate-500">{t.academic_year}</div>
						<div class="text-slate-500">{t.starts_at}</div>
						<div class="text-slate-500">{t.ends_at}</div>
					</div>
				{/each}
			</div>

			<!-- ================================================================ -->
			<!-- DANIŞMAN                                                          -->
			<!-- ================================================================ -->
		{:else if apiKey === 'advisor' && advisor?.advisor}
			<div
				class="rounded-xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="flex items-start gap-5">
					<div
						class="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-400 to-indigo-600 text-2xl font-bold text-white shadow"
					>
						{advisor.advisor.name.charAt(0)}
					</div>
					<div class="flex-1">
						<div class="text-xl font-bold">{advisor.advisor.name}</div>
						{#if advisor.advisor.title}<div class="mt-0.5 text-sm text-slate-500">
								{advisor.advisor.title}
							</div>{/if}
					</div>
				</div>
				<div class="mt-5 grid grid-cols-2 gap-3">
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
				class="mb-2 flex items-center justify-between rounded-xl border border-black/10 bg-white px-5 py-3 shadow-sm dark:border-white/10 dark:bg-white/5"
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
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Kod</th>
								<th class="px-4 py-3 text-left">Ders Adı</th>
								<th class="px-4 py-3 text-center">K</th>
								<th class="px-4 py-3 text-center">AKTS</th>
								<th class="px-4 py-3 text-left">Öğretim Elemanı</th>
								<th class="px-4 py-3 text-left">Gün / Saat</th>
								<th class="px-4 py-3 text-left">Derslik</th>
							</tr>
						</thead>
						<tbody>
							{#each enrollments as e}
								<tr
									class="border-t border-black/5 hover:bg-slate-50/50 transition-colors dark:border-white/10 dark:hover:bg-white/5"
								>
									<td
										class="px-4 py-3 font-mono text-xs font-semibold text-slate-600 dark:text-slate-300"
										>{e.course_code}</td
									>
									<td class="px-4 py-3 font-medium">{e.course_name}</td>
									<td class="px-4 py-3 text-center text-slate-500">{e.credits}</td>
									<td class="px-4 py-3 text-center font-semibold">{e.akts}</td>
									<td class="px-4 py-3 text-xs text-slate-500">{e.instructor_name ?? '—'}</td>
									<td class="px-4 py-3 text-xs"
										>{e.day_of_week ?? '—'} {e.start_time ?? ''}–{e.end_time ?? ''}</td
									>
									<td class="px-4 py-3 text-xs text-slate-500">{e.classroom ?? '—'}</td>
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
					<span class="font-semibold">{enrollmentTermLabel} — AKTS Durumu</span>
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

			{#if hasPendingRegistration}
				<div
					class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200"
				>
					<strong>Danışman onayında:</strong> Ders seçiminiz kilitli. Danışmanınız kesinleştirdiğinde
					kayıtlarınız <strong>Kesinleştirildi</strong> olarak görünecek; haftalık programınız güncellenir
					(<a href="/obs/ogrenci/ders-programi" class="underline font-semibold">Ders programı</a>).
				</div>
			{/if}

			{#if enrollments.some((e) => e.status === 'active')}
				<div
					class="mt-3 rounded-xl border border-emerald-100 bg-emerald-50/80 px-5 py-3 text-sm text-emerald-900 dark:border-emerald-900/30 dark:bg-emerald-950/20 dark:text-emerald-200"
				>
					<span class="font-semibold">Kesinleşen dersler ({enrollments.filter((e) => e.status === 'active').length}):</span>
					<span class="text-emerald-800 dark:text-emerald-300">
						{enrollments
							.filter((e) => e.status === 'active')
							.map((e) => e.course_code)
							.join(', ')}</span
					>
				</div>
			{/if}

			<!-- Sepet / Gönder -->
			{#if draftEnrollments.length}
				<div
					class="mt-3 rounded-xl border border-emerald-200 bg-emerald-50/80 px-5 py-4 dark:border-emerald-900/40 dark:bg-emerald-950/20"
				>
					<div class="mb-3 flex items-center justify-between">
						<span class="font-semibold text-emerald-800 dark:text-emerald-200"
							>Taslak kayıt listesi ({draftEnrollments.length} ders · {draftAkts} AKTS)</span
						>
						<button
							on:click={clearAllDraftEnrollments}
							disabled={hasPendingRegistration}
							type="button"
							class="text-xs text-emerald-600 hover:text-emerald-800 dark:text-emerald-400 disabled:opacity-40"
							>Temizle</button
						>
					</div>
					<div class="mb-3 space-y-1.5">
						{#each draftEnrollments as e}
							<div
								class="flex items-center justify-between rounded-lg bg-white/70 px-3 py-2 dark:bg-white/5"
							>
								<span class="font-mono text-xs font-semibold text-slate-500 mr-2"
									>{e.course_code}</span
								>
								<span class="flex-1 text-sm font-medium">{e.course_name}</span>
								<span class="mx-3 text-xs text-slate-400">{e.akts} AKTS</span>
								<button
									on:click={() => removeDraftEnrollmentRow(e.id)}
									disabled={hasPendingRegistration}
									type="button"
									class="text-red-400 hover:text-red-600 text-sm disabled:opacity-40">✕</button
								>
							</div>
						{/each}
					</div>
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
						class="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 py-2.5 text-sm font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
					>
						{#if enrollSubmitting}
							<div
								class="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
							></div>
						{/if}
						{enrollSubmitting
							? 'Gönderiliyor…'
							: 'Danışman onayına gönder'}
					</button>
				</div>
			{:else if enrollSuccess}
				<div
					class="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200"
				>
					{enrollSuccess}
				</div>
			{/if}

			<!-- Açılan dersler tablosu -->
			<div
				class="mt-3 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="flex items-center justify-between border-b border-black/5 px-5 py-3 dark:border-white/10"
				>
					<div class="text-sm font-bold text-slate-600 dark:text-slate-300">Açılan Dersler</div>
					<div class="text-xs text-slate-400">{availableCourses.length} ders mevcut</div>
				</div>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Kod</th>
								<th class="px-4 py-3 text-left">Ders Adı</th>
								<th class="px-4 py-3 text-center">AKTS</th>
								<th class="px-4 py-3 text-left text-xs">Öncelik</th>
								<th class="px-4 py-3 text-left">Öğr. Elemanı</th>
								<th class="px-4 py-3 text-left">Gün/Saat</th>
								<th class="px-4 py-3 text-center">Kontenjan</th>
								<th class="px-4 py-3 text-center"></th>
							</tr>
						</thead>
						<tbody>
							{#each availableCourses as c}
								{@const inCart = enrollments.some(
									(x) =>
										x.status === 'draft' &&
										x.section_id === c.id &&
										(x.enrollment_reason || '') !== 'add_drop'
								)}
								{@const full = c.enrolled >= c.capacity}
								<tr
									class="border-t border-black/5 dark:border-white/10 {inCart
										? 'bg-sky-50/50 dark:bg-sky-900/10'
										: 'hover:bg-slate-50/50 dark:hover:bg-white/5'} transition-colors"
								>
									<td class="px-4 py-3 font-mono text-xs font-semibold text-slate-500"
										>{c.course_code}</td
									>
									<td class="px-4 py-3 font-medium">{c.course_name}</td>
									<td class="px-4 py-3 text-center font-semibold">{c.akts}</td>
									<td
										class="px-4 py-3 text-[10px] leading-tight text-slate-600 dark:text-slate-400"
										title={c.registration_priority_label ?? ''}
									>
										<span class="font-mono font-semibold">{c.registration_priority_tier ?? '—'}</span>
										{#if c.registration_priority_label}
											<div class="max-w-[7rem] truncate">{c.registration_priority_label}</div>
										{/if}
									</td>
									<td class="px-4 py-3 text-xs text-slate-500">{c.instructor_name}</td>
									<td class="px-4 py-3 text-xs">{c.day_of_week} {c.start_time}–{c.end_time}</td>
									<td
										class="px-4 py-3 text-center text-xs {full ? 'text-red-500' : 'text-slate-500'}"
									>
										{c.enrolled}/{c.capacity}
										{#if full}<span
												class="ml-1 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-900/40 dark:text-red-300"
												>Dolu</span
											>{/if}
									</td>
									<td class="px-4 py-3 text-center">
										{#if full && !inCart}
											<span class="text-xs text-slate-300">—</span>
										{:else if hasPendingRegistration}
											<span class="text-xs text-slate-400" title="Liste kilitli">Kilitli</span>
										{:else}
											<button
												type="button"
												on:click={() => toggleCart(c)}
												class="rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors
													{inCart
													? 'bg-sky-100 text-sky-700 ring-1 ring-sky-300 dark:bg-sky-900/40 dark:text-sky-300'
													: 'bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20'}"
											>
												{inCart ? 'Taslakta' : 'Ders ekle'}
											</button>
										{/if}
									</td>
								</tr>
							{:else}
								<tr
									><td colspan="7" class="px-4 py-8 text-center text-sm text-slate-400"
										>Açılan ders bulunamadı.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
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
			<div
				class="rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div
					class="flex flex-wrap items-center justify-between gap-2 border-b border-black/5 px-5 py-3 dark:border-white/10"
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
									: !addDropAktsOk
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

				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="w-8 px-4 py-3"></th>
								<th class="px-4 py-3 text-left">Kod</th>
								<th class="px-4 py-3 text-left">Ders Adı</th>
								<th class="px-4 py-3 text-left">Durum</th>
								<th class="px-4 py-3 text-center">AKTS</th>
								<th class="px-4 py-3 text-left text-xs">Önc.</th>
								<th class="px-4 py-3 text-left">Öğr. Elemanı</th>
								<th class="px-4 py-3 text-left">Gün/Saat</th>
								<th class="px-4 py-3"></th>
							</tr>
						</thead>
						<tbody>
							{#each enrollments.filter((x) => ['active', 'pending_drop', 'pending', 'draft'].includes(x.status) && (x.status !== 'draft' || (x.enrollment_reason || '') === 'add_drop')) as e}
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
										class="px-4 py-3 font-mono text-xs font-semibold {marked
											? 'text-red-500'
											: 'text-slate-500'}"
									>
										{e.course_code}
									</td>
									<td
										class="px-4 py-3 font-medium {marked || st === 'pending_drop'
											? 'text-slate-500 line-through'
											: ''}"
									>
										{e.course_name}
									</td>
									<td class="px-4 py-3">
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
									</td>
									<td class="px-4 py-3 text-center">{e.akts}</td>
									<td
										class="px-4 py-3 text-[10px] leading-tight text-slate-500"
										title={e.registration_priority_label ?? ''}
									>
										<span class="font-mono font-semibold">{e.registration_priority_tier ?? '—'}</span>
										{#if e.registration_priority_label}
											<div class="max-w-[6.5rem] truncate">{e.registration_priority_label}</div>
										{/if}
									</td>
									<td class="px-4 py-3 text-xs text-slate-500">{e.instructor_name ?? '—'}</td>
									<td class="px-4 py-3 text-xs">
										{e.day_of_week ?? '—'} {e.start_time ?? ''}
									</td>
									<td class="px-4 py-3 text-right">
										{#if st === 'draft' && !hasPendingAddDrop}
											<button
												type="button"
												class="text-xs font-semibold text-red-600 hover:underline"
												on:click={() => removeDraftEnrollmentRow(eId)}>Eklemeyi iptal et</button>
										{/if}
									</td>
								</tr>
							{:else}
								<tr
									><td colspan="9" class="px-4 py-8 text-center text-sm text-slate-400"
										>Henüz satır yok.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
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
					class="flex items-center justify-between border-b border-black/5 px-5 py-3 dark:border-white/10"
				>
					<div class="text-sm font-bold text-slate-600 dark:text-slate-300">
						Ders ekle-bırak için açılan şubeler
					</div>
					<div class="text-xs text-slate-400">{availableCourses.length} şube</div>
				</div>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Kod</th>
								<th class="px-4 py-3 text-left">Ders Adı</th>
								<th class="px-4 py-3 text-center">AKTS</th>
								<th class="px-4 py-3 text-left text-xs">Öncelik</th>
								<th class="px-4 py-3 text-left">Öğr. Elemanı</th>
								<th class="px-4 py-3 text-left">Gün/Saat</th>
								<th class="px-4 py-3 text-center">Kontenjan</th>
								<th class="px-4 py-3 text-center"></th>
							</tr>
						</thead>
						<tbody>
							{#each availableCourses as c}
								{@const inCart = enrollments.some(
									(x) => x.status === 'draft' && x.section_id === c.id
								)}
								{@const full = c.enrolled >= c.capacity}
								<tr
									class="border-t border-black/5 dark:border-white/10 {inCart
										? 'bg-sky-50/50 dark:bg-sky-900/10'
										: 'hover:bg-slate-50/50 dark:hover:bg-white/5'} transition-colors"
								>
									<td class="px-4 py-3 font-mono text-xs font-semibold text-slate-500"
										>{c.course_code}</td
									>
									<td class="px-4 py-3 font-medium">{c.course_name}</td>
									<td class="px-4 py-3 text-center font-semibold">{c.akts}</td>
									<td
										class="px-4 py-3 text-[10px] leading-tight text-slate-600 dark:text-slate-400"
										title={c.registration_priority_label ?? ''}
									>
										<span class="font-mono font-semibold">{c.registration_priority_tier ?? '—'}</span>
										{#if c.registration_priority_label}
											<div class="max-w-[7rem] truncate">{c.registration_priority_label}</div>
										{/if}
									</td>
									<td class="px-4 py-3 text-xs text-slate-500">{c.instructor_name}</td>
									<td class="px-4 py-3 text-xs">{c.day_of_week} {c.start_time}–{c.end_time}</td>
									<td
										class="px-4 py-3 text-center text-xs {full ? 'text-red-500' : 'text-slate-500'}"
									>
										{c.enrolled}/{c.capacity}
										{#if full}<span
												class="ml-1 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-900/40 dark:text-red-300"
												>Dolu</span
											>{/if}
									</td>
									<td class="px-4 py-3 text-center">
										{#if full && !inCart}
											<span class="text-xs text-slate-300">—</span>
										{:else if hasPendingAddDrop}
											<span class="text-xs text-slate-400" title="Talep kilitli">Kilitli</span>
										{:else}
											<button
												type="button"
												on:click={() => toggleAddDropCart(c)}
												class="rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors
													{inCart
													? 'bg-sky-100 text-sky-700 ring-1 ring-sky-300 dark:bg-sky-900/40 dark:text-sky-300'
													: 'bg-slate-100 text-slate-600 hover:bg-sky-50 hover:text-sky-700 dark:bg-white/10 dark:hover:bg-sky-900/20'}"
											>
												{inCart ? 'Taslakta' : 'Ders ekle'}
											</button>
										{/if}
									</td>
								</tr>
							{:else}
								<tr
									><td colspan="7" class="px-4 py-8 text-center text-sm text-slate-400"
										>Açılan ders bulunamadı.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			<!-- ================================================================ -->
			<!-- SINAV TAKVİMİ                                                     -->
			<!-- ================================================================ -->
		{:else if apiKey === 'exams'}
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-left">Tür</th>
								<th class="px-4 py-3 text-left">Tarih</th>
								<th class="px-4 py-3 text-left">Saat</th>
								<th class="px-4 py-3 text-left">Derslik</th>
								<th class="px-4 py-3 text-center">Ağırlık</th>
							</tr>
						</thead>
						<tbody>
							{#each exams as ex}
								<tr
									class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 transition-colors"
								>
									<td class="px-4 py-3 font-mono text-xs font-semibold">{ex.course_code}</td>
									<td class="px-4 py-3">
										<span
											class="rounded-full px-2 py-0.5 text-xs font-medium
											{ex.exam_type === 'midterm'
												? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300'
												: ex.exam_type === 'final'
													? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
													: 'bg-slate-100 text-slate-600'}"
										>
											{ex.exam_type === 'midterm'
												? 'Vize'
												: ex.exam_type === 'final'
													? 'Final'
													: ex.exam_type}
										</span>
									</td>
									<td class="px-4 py-3 font-medium">{ex.exam_date}</td>
									<td class="px-4 py-3 text-slate-500">{ex.exam_time}</td>
									<td class="px-4 py-3 text-xs text-slate-500">{ex.classroom}</td>
									<td class="px-4 py-3 text-center font-semibold"
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
			<div class="space-y-3">
				{#each DAYS as day}
					{@const rows = schedule.filter((s) => s.day === day)}
					{#if rows.length}
						<div
							class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
						>
							<div
								class="bg-slate-100/70 px-5 py-2 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								{day}
							</div>
							{#each rows as s}
								<div
									class="flex items-center gap-4 border-t border-black/5 px-5 py-3 dark:border-white/10"
								>
									<span class="w-28 shrink-0 font-mono text-xs text-slate-400"
										>{s.start}–{s.end}</span
									>
									<span
										class="rounded-lg bg-sky-100 px-2 py-0.5 font-mono text-xs font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
										>{s.course_code}</span
									>
									<span class="flex-1 text-sm font-medium">{s.course_name}</span>
									<span class="shrink-0 text-xs text-slate-400">{s.classroom}</span>
								</div>
							{/each}
						</div>
					{/if}
				{/each}
				{#if !schedule.length}
					<div
						class="rounded-xl border border-dashed border-black/15 p-8 text-center text-sm text-slate-400"
					>
						Ders programı yüklenemedi.
					</div>
				{/if}
			</div>

			<!-- ================================================================ -->
			<!-- NOT LİSTESİ                                                       -->
			<!-- ================================================================ -->
		{:else if apiKey === 'grades'}
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-center">Vize</th>
								<th class="px-4 py-3 text-center">Final</th>
								<th class="px-4 py-3 text-center">Harf</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each grades as g}
								<tr
									class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 transition-colors"
								>
									<td
										class="px-4 py-3 font-mono text-xs font-semibold text-slate-600 dark:text-slate-300"
										>{g.course_code}</td
									>
									<td class="px-4 py-3 text-center">{g.midterm ?? '—'}</td>
									<td class="px-4 py-3 text-center">{g.final ?? '—'}</td>
									<td class="px-4 py-3 text-center">
										{#if g.is_published && g.letter_grade}
											<span
												class="rounded-full px-2.5 py-0.5 text-xs font-bold {GRADE_COLOR[
													g.letter_grade
												] ?? 'bg-slate-100 text-slate-600'}">{g.letter_grade}</span
											>
										{:else}<span class="text-slate-300">—</span>{/if}
									</td>
									<td class="px-4 py-3 text-center text-xs">
										{#if g.is_published}<span class="text-emerald-600 dark:text-emerald-400"
												>Yayınlandı</span
											>
										{:else if g.is_finalized}<span class="text-amber-600 dark:text-amber-400"
												>Kesinleşti</span
											>
										{:else}<span class="text-slate-400">Bekleniyor</span>{/if}
									</td>
								</tr>
							{:else}
								<tr
									><td colspan="5" class="px-4 py-8 text-center text-sm text-slate-400"
										>Not bulunamadı.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
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
					<div
						class="grid grid-cols-3 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
					>
						<div>Dönem</div>
						<div class="text-center">DNO</div>
						<div class="text-center">AKTS</div>
					</div>
					{#each gpaTerms as { term_name: string; term_gpa: number | null; akts_completed: number }[] as t}
						<div
							class="grid grid-cols-3 border-t border-black/5 px-5 py-3.5 text-sm dark:border-white/10"
						>
							<div class="font-medium">{t.term_name}</div>
							<div
								class="text-center font-bold {t.term_gpa && t.term_gpa >= 2.0
									? 'text-emerald-600 dark:text-emerald-400'
									: 'text-red-600 dark:text-red-400'}"
							>
								{t.term_gpa?.toFixed(2) ?? '—'}
							</div>
							<div class="text-center text-slate-500">{t.akts_completed}</div>
						</div>
					{/each}
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
					class="border-b border-black/10 bg-slate-50 px-6 py-4 dark:border-white/10 dark:bg-white/5 print:bg-white"
				>
					<div class="flex items-start justify-between gap-4">
						<div>
							<div class="text-xs font-bold uppercase tracking-widest text-slate-400">
								Doğuş Üniversitesi
							</div>
							<div class="mt-1 text-lg font-bold text-slate-900 dark:text-slate-100">
								Akademik Transkript
							</div>
							<div class="mt-1 text-sm text-slate-500">
								{profile?.full_name ?? $user?.name ?? '—'} · No: {profile?.student_no ?? '—'}
							</div>
							<div class="text-xs text-slate-400">
								{profile?.department ?? '—'} · {profile?.program ?? 'Lisans'}
							</div>
						</div>
						<div class="flex items-center gap-5 shrink-0">
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
					<div class="flex items-center justify-between bg-slate-100 px-5 py-3 dark:bg-white/10">
						<div class="font-semibold text-slate-700 dark:text-slate-200">{term.term_name}</div>
						<div class="flex gap-4 text-xs text-slate-500">
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
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="bg-slate-50/80 text-xs font-semibold text-slate-500 dark:bg-white/5">
								<tr>
									<th class="px-5 py-2 text-left">Ders Kodu</th>
									<th class="px-5 py-2 text-left">Ders Adı</th>
									<th class="px-5 py-2 text-center">Kredi</th>
									<th class="px-5 py-2 text-center">AKTS</th>
									<th class="px-5 py-2 text-center">Not Puanı</th>
									<th class="px-5 py-2 text-center">Harf Notu</th>
								</tr>
							</thead>
							<tbody>
								{#each term.courses as c}
									<tr class="border-t border-black/5 dark:border-white/10">
										<td class="px-5 py-2.5 font-mono text-xs font-semibold text-slate-500"
											>{c.code}</td
										>
										<td class="px-5 py-2.5 font-medium">{c.name}</td>
										<td class="px-5 py-2.5 text-center text-xs text-slate-400">{c.credits}</td>
										<td class="px-5 py-2.5 text-center text-xs text-slate-400">{c.akts}</td>
										<td class="px-5 py-2.5 text-center text-xs text-slate-500"
											>{c.grade_point.toFixed(2)}</td
										>
										<td class="px-5 py-2.5 text-center">
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
						<div class="flex items-center justify-between gap-4">
							<div>
								<div class="text-xs font-semibold text-slate-500 dark:text-slate-400">Program</div>
								<div class="mt-1 text-sm font-bold">{curriculum.program ?? '—'}</div>
							</div>
							<div class="text-right">
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
							Bu liste yalnızca <strong class="font-semibold text-slate-600 dark:text-slate-300"
								>obs_course_enrollments</strong
							> tablosundaki şube kayıtlarınızdan üretilir. Tam diploma müfredatı (alınmamış tüm zorunlu/seçmeli
							dersler) ayrı bir program tablosu olmadan gösterilmez; gördüğünüz her satır için veritabanında
							kayıt vardır.
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
							<div class="flex items-center justify-between bg-slate-50 px-5 py-3 dark:bg-white/5">
								<div class="font-semibold">{cat.name}</div>
								<div class="text-xs text-slate-500">
									{done}/{total} tamamlandı
									{#if ongoing > 0}<span
											class="ml-1.5 rounded-full bg-sky-100 px-1.5 py-0.5 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
											>{ongoing} devam</span
										>{/if}
								</div>
							</div>
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
									<div class="col-span-6 font-medium">{c.name}</div>
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
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Ders</th>
								<th class="px-4 py-3 text-center">Toplam</th>
								<th class="px-4 py-3 text-center">Devamsız</th>
								<th class="px-4 py-3 text-center">Devam %</th>
								<th class="px-4 py-3 text-center">Durum</th>
							</tr>
						</thead>
						<tbody>
							{#each attendance as a}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3">
										<div class="font-mono text-xs font-semibold">{a.course_code}</div>
										<div class="text-xs text-slate-400">{a.course_name}</div>
									</td>
									<td class="px-4 py-3 text-center">{a.total_weeks}</td>
									<td
										class="px-4 py-3 text-center font-semibold {a.absent_count > 3
											? 'text-red-500'
											: ''}">{a.absent_count}</td
									>
									<td class="px-4 py-3 text-center">
										<div
											class="font-bold {a.attendance_pct >= 70
												? 'text-emerald-600 dark:text-emerald-400'
												: 'text-red-600 dark:text-red-400'}"
										>
											%{a.attendance_pct.toFixed(1)}
										</div>
										<div
											class="mt-1 h-1.5 w-16 mx-auto overflow-hidden rounded-full bg-slate-200 dark:bg-white/10"
										>
											<div
												class="h-full rounded-full transition-all {a.attendance_pct >= 70
													? 'bg-emerald-500'
													: 'bg-red-500'}"
												style="width:{a.attendance_pct}%"
											></div>
										</div>
									</td>
									<td class="px-4 py-3 text-center">
										<span
											class="rounded-full px-2.5 py-0.5 text-xs font-medium
											{a.status === 'ok'
												? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
												: a.status === 'warning'
													? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
													: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}"
										>
											{a.status === 'ok' ? 'İyi' : a.status === 'warning' ? 'Uyarı' : 'Kritik'}
										</span>
									</td>
								</tr>
							{:else}
								<tr
									><td colspan="5" class="px-4 py-8 text-center text-sm text-slate-400"
										>Devamsızlık kaydı yok.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
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
								<div class="font-semibold">{ann.title}</div>
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
			<div class="flex items-center justify-between">
				<span class="text-xs text-slate-400">{msgs.length} mesaj</span>
				<button
					on:click={() => (showCompose = true)}
					type="button"
					class="flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
				>
					✏ Yeni Mesaj
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
								class="font-semibold text-sm {apiKey === 'inbox' && !m.is_read
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
								: `→ ${m.receiver_name ?? m.receiver_type}`} · {m.sent_at}
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
					class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
				>
					<div
						class="w-full max-w-lg rounded-2xl border border-black/10 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-slate-900"
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
									<div class="flex items-center justify-between">
										<span class="font-medium text-sm"
											>{req.document_type} — {req.document_subtype}</span
										>
										<span
											class="rounded-full px-2 py-0.5 text-xs {req.status === 'tamamlandı'
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
			class="fixed bottom-6 right-6 z-40 flex h-11 w-11 items-center justify-center rounded-full bg-sky-500 text-white shadow-lg hover:bg-sky-400 transition-all hover:scale-105"
		>
			✏
		</button>
	{/if}

	<!-- Compose modal (sayfa dışından açılınca) -->
	{#if showCompose && !['inbox', 'sent'].includes(apiKey)}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
			<div
				class="w-full max-w-lg rounded-2xl border border-black/10 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-slate-900"
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
