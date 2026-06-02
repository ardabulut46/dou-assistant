/**
 * OBS akademik API istemcisi — uçlar Open WebUI altında PostgreSQL obs_* verisine bağlıdır.
 */

import { getWebuiApiBaseUrl } from '$lib/constants';

// ---------------------------------------------------------------------------
// Yardımcı
// ---------------------------------------------------------------------------

async function authFetch<T>(path: string, token: string | null, options?: RequestInit): Promise<T> {
	if (!token) throw new Error('Oturum tokeni yok');

	const apiBase = getWebuiApiBaseUrl();
	const res = await fetch(`${apiBase}${path}`, {
		...options,
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`,
			...(options?.headers ?? {})
		},
		credentials: 'include'
	});

	const text = await res.text();
	let data: unknown = {};
	if (text.trim()) {
		try {
			data = JSON.parse(text.replace(/^\uFEFF/, ''));
		} catch {
			throw new Error(`HTTP ${res.status}: JSON bekleniyordu (${path})`);
		}
	}

	if (!res.ok) {
		const raw = (data as { detail?: unknown })?.detail;
		let msg: string;
		if (typeof raw === 'string') {
			msg = raw;
		} else if (Array.isArray(raw) && raw.length > 0) {
			const first = raw[0] as { msg?: string; message?: string };
			msg = first?.msg ?? first?.message ?? JSON.stringify(raw);
		} else if (raw != null) {
			msg = JSON.stringify(raw);
		} else {
			msg = `HTTP ${res.status}: ${res.statusText}`;
		}
		throw new Error(msg);
	}

	return data as T;
}

// ---------------------------------------------------------------------------
// Tipler
// ---------------------------------------------------------------------------

export type DouTerm = {
	id: string;
	name: string;
	academic_year: string;
	season: string;
	starts_at: string;
	ends_at: string;
	is_active?: boolean;
	registration_open?: boolean | null;
	registration_start?: string;
	registration_end?: string;
	add_drop_open?: boolean | null;
	add_drop_start?: string;
	add_drop_end?: string;
};

export type DouDepartment = { id: string; code: string; name: string };

export type DouStudentProfile = {
	user_id: string;
	email: string;
	full_name?: string;
	student_no: string;
	department_id: string;
	department_name: string;
	faculty_name?: string;
	program: string;
	class_level: number;
	/** Program yarıyılı (1 tabanlı); kayıt üst sınırı için. */
	program_semester_number?: number;
	gpa?: number;
	status?: string;
	enrollment_date?: string;
	is_financially_eligible?: boolean;
	_mock?: boolean;
	/** obs_student_profiles satırı yok; yönetimden özlük eklenmeli */
	_obs_profile_missing?: boolean;
};

export type DouAdvisor = {
	academic_user_id: string;
	name: string;
	title?: string;
	email: string;
	department_id: string;
	department_name?: string;
	office?: string;
	phone?: string;
	/** Danışmanlık / ofis görüşme saatleri */
	consulting_hours?: string;
};

export type DouAdvisorResponse = {
	student_user_id: string;
	advisor: DouAdvisor | null;
	valid_from?: string | null;
	valid_to?: string | null;
	_mock?: boolean;
};

export type DouEnrollment = {
	id: string;
	student_id: string;
	course_id?: string;
	section_id: string;
	course_code: string;
	course_name: string;
	instructor_name?: string;
	credits: number;
	akts: number;
	term_id: string;
	classroom?: string;
	day_of_week?: string;
	start_time?: string;
	end_time?: string;
	section_no?: number;
	theory_hours?: string;
	language?: string;
	class_year?: number;
	type?: string;
	/** API: obs_courses.is_mandatory + type (zorunlu/required). */
	is_mandatory_course?: boolean;
	status: string;
	/** Taslak satırda: registration | add_drop | advisor_added … */
	enrollment_reason?: string;
	/** OBS: Müfredatta öğrencinin program yarıyılı kartıyla eşleşiyor mu (ders ekle-bırak AKTS özeti ile uyumlu). */
	add_drop_curriculum_slot_match?: boolean;
};

export type DouEnrollmentsResponse = {
	student_user_id: string;
	term_id_filter: string | null;
	enrollments: DouEnrollment[];
	total_akts?: number;
	_mock?: boolean;
};

export type DouGradeEntry = {
	enrollment_id: string;
	course_code: string;
	course_name: string;
	term_id: string;
	term_name?: string;
	/** Şubede akademisyen tarafından tanımlı vize sınav yüzdesi (yoksa API 40 döner). */
	midterm_weight_percent?: number;
	/** Şubede tanımlı final sınav yüzdesi (yoksa 60). */
	final_weight_percent?: number;
	midterm: number | null;
	final: number | null;
	makeup: number | null;
	letter_grade: string | null;
	is_published: boolean;
	is_finalized: boolean;
};

export type DouGradesResponse = {
	student_user_id: string;
	grades: DouGradeEntry[];
	_mock?: boolean;
};

export type DouGpaSummary = {
	student_user_id: string;
	cumulative_gpa: number | null;
	total_akts_completed: number;
	class_level: number;
	terms: Array<{
		term_id: string;
		term_name: string;
		term_gpa: number | null;
		akts_completed: number;
		akts_passed: number;
	}>;
	_mock?: boolean;
};

export type DouTranscriptCourse = {
	code: string;
	name: string;
	credits: number;
	akts: number;
	letter: string;
	grade_point: number;
};

export type DouTranscriptTerm = {
	term_name: string;
	courses: DouTranscriptCourse[];
	term_gpa: number;
	term_akts: number;
};

export type DouTranscriptResponse = {
	student_user_id: string;
	cumulative_gpa: number;
	total_akts: number;
	transcript: DouTranscriptTerm[];
	_mock?: boolean;
};

export type DouScheduleRow = {
	day: string;
	start: string;
	end: string;
	course_code: string;
	course_name: string;
	classroom: string;
	instructor: string;
};

export type DouScheduleResponse = {
	student_user_id: string;
	term_id: string;
	schedule: DouScheduleRow[];
	_mock?: boolean;
};

export type DouExam = {
	id: string;
	course_code: string;
	course_name: string;
	exam_type: string;
	exam_date: string;
	exam_time: string;
	classroom: string;
	weight_percent: number;
};

export type DouAttendanceRow = {
	course_code: string;
	course_name: string;
	total_weeks: number;
	absent_count: number;
	attendance_pct: number;
	status: 'ok' | 'warning' | 'fail';
	/** Toplam hafta içinde en fazla izin verilen devamsız (≈ %30, aşağı yuvarlak). */
	allowed_absences_30pct?: number;
	/** limiti aşan devamsızlık sayısı (0 ise sınır içi). */
	absences_over_30pct?: number;
	/** Sınır dahilinde daha kaç eksik hakkı olduğu. */
	absences_remain_under_30pct?: number;
};

export type DouDocumentRequest = {
	id: string;
	requesting_institution: string;
	request_reason: string;
	document_type: string;
	document_subtype: string;
	status: string;
	created_at: string;
};

export type DouSection = {
	id: string;
	course_id: string;
	course_code: string;
	course_name: string;
	section_code: string;
	section_no: number;
	term_id: string;
	instructor_id: string;
	instructor_name?: string;
	classroom: string;
	day_of_week: string;
	start_time: string;
	end_time: string;
	enrollment_count: number;
	capacity: number;
	midterm_weight_percent?: number;
	final_weight_percent?: number;
};

export type DouClassroomOption = {
	id: string;
	/** Seçenek değeri (kod veya yalnızca ad) */
	code: string;
	/** Görünen metin (kapasite / bina ekli) */
	label?: string;
	capacity?: number | null;
};

export type DouAcademicSectionsResponse = {
	academic_user_id: string;
	term_id_filter: string | null;
	sections: DouSection[];
	/** `include_classrooms=true` ile (sınav tanımlama derslik dropdown) */
	classrooms?: DouClassroomOption[];
	_mock?: boolean;
};

export type DouMessage = {
	id: string;
	sender_user_id?: string;
	sender_name?: string;
	sender_type?: string;
	receiver_user_id?: string;
	receiver_name?: string;
	receiver_type?: string;
	subject: string;
	body: string;
	is_read: boolean;
	status: string;
	sent_at: string;
};

export type DouMessagesResponse = {
	user_id: string;
	messages: DouMessage[];
	total: number;
	_mock?: boolean;
};

export type DouAddDropCourseLine = {
	enrollment_id: string;
	course_code: string;
	course_name: string;
	akts: number;
};

export type DouAddDropApprovalDetail = {
	student_user_id: string;
	student_name: string;
	student_no: string;
	department_name: string;
	term_id: string;
	term_name: string;
	agno: number | null;
	akts_min: number;
	akts_max: number;
	projected_akts: number;
	added_courses: DouAddDropCourseLine[];
	dropped_courses: DouAddDropCourseLine[];
	kept_courses: DouAddDropCourseLine[];
};

export type DouApprovalRequest = {
	id: string;
	student_user_id?: string;
	student_name: string;
	student_no: string;
	request_type: string;
	related_enrollment_id?: string;
	course_code?: string;
	course_name?: string;
	status: string;
	note?: string | null;
	created_at: string;
	/** schedule_batch + add_drop talepleri için danışman özeti */
	add_drop_detail?: DouAddDropApprovalDetail;
};

export type DouCalendarEvent = {
	id: string;
	term_id: string;
	event_type: string;
	title: string;
	start_date: string;
	end_date: string;
};

export type DouAnnouncement = {
	id: string;
	title: string;
	content: string;
	audience_type: string;
	department_id?: string | null;
	course_section_id?: string | null;
	/** Belirli öğrenci hedefi (backend `student_number` / `student_no`) */
	student_no?: string | null;
	is_active: boolean;
	published_at?: string | null;
	created_at?: string | null;
	created_by?: string;
	/** JOIN user.name — gösterim için */
	created_by_name?: string | null;
};

export type DouAdminStats = {
	departments: number;
	terms: number;
	courses: number;
	classrooms: number;
	sections: number;
	announcements?: number;
	_mock?: boolean;
};

// ---------------------------------------------------------------------------
// Ortak
// ---------------------------------------------------------------------------

export const getDouTerms = (token: string | null) => authFetch<DouTerm[]>('/terms', token);

export const getDouTermCalendar = (token: string | null, termId: string) =>
	authFetch<{ term_id: string; events: DouCalendarEvent[]; _mock?: boolean }>(
		`/terms/${termId}/calendar`,
		token
	);

export const getDouDepartments = (token: string | null) =>
	authFetch<DouDepartment[]>('/departments', token);

export const getDouAnnouncements = (
	token: string | null,
	params?: { audience_type?: string; department_id?: string }
) => {
	const q = new URLSearchParams(params as Record<string, string>).toString();
	return authFetch<{ announcements: DouAnnouncement[]; _mock?: boolean }>(
		`/announcements${q ? `?${q}` : ''}`,
		token
	);
};

// ---------------------------------------------------------------------------
// Mesajlar
// ---------------------------------------------------------------------------

export const getDouInbox = (token: string | null, senderType?: string) => {
	const q = senderType ? `?sender_type=${encodeURIComponent(senderType)}` : '';
	return authFetch<DouMessagesResponse>(`/messages/inbox${q}`, token);
};

export const getDouSent = (token: string | null, receiverType?: string) => {
	const q = receiverType ? `?receiver_type=${encodeURIComponent(receiverType)}` : '';
	return authFetch<DouMessagesResponse>(`/messages/sent${q}`, token);
};

export const sendDouMessage = (
	token: string | null,
	body: {
		receiver_user_id: string;
		receiver_name?: string;
		receiver_type?: string;
		subject: string;
		body: string;
	}
) => authFetch<DouMessage>('/messages', token, { method: 'POST', body: JSON.stringify(body) });

export const markDouMessageRead = (token: string | null, messageId: string) =>
	authFetch<{ id: string; is_read: boolean }>(`/messages/${messageId}/read`, token, {
		method: 'PATCH'
	});

export const deleteDouMessage = (token: string | null, messageId: string) =>
	authFetch<{ id: string; status: string }>(`/messages/${messageId}`, token, { method: 'DELETE' });

// ---------------------------------------------------------------------------
// Öğrenci
// ---------------------------------------------------------------------------

export const getDouStudentProfile = (token: string | null) =>
	authFetch<DouStudentProfile>('/student/me/profile', token);

export const getDouStudentAdvisor = (token: string | null) =>
	authFetch<DouAdvisorResponse>('/student/me/advisor', token);

/** Müfredatta eksik görünen zorunlu ders satırı (/registration-limits). */
export type CurriculumMandatoryBrief = {
	course_id: string;
	course_code: string;
	course_name: string;
	akts: number;
	/** obs_courses.curriculum_semester; müfredat kartı sırası (yüksek lisans dahil doğrudan sıra kullanılacaksa null olabilir). */
	curriculum_semester?: number | null;
};

export type DouStudentRegistrationLimits = {
	student_user_id: string;
	term_id: string;
	akts_max: number;
	rule: string;
	/** Limit kuralında kullanılan GNO: önce AKTS ağırlıklı hesap, yoksa profil. */
	gpa: number | null;
	/** Σ(not×AKTS)/ΣAKTS; transkriptle aynı satır kümesi. */
	gpa_computed: number | null;
	gpa_profile: number | null;
	akts_counted_in_gpa: number;
	is_prep: boolean;
	current_term_akts: number;
	akts_limit_default: number;
	akts_limit_high: number;
	akts_limit_top: number;
	akts_limit_prep: number;
	min_gpa_for_high_akts: number;
	min_gpa_for_top_akts: number;
	program_semester_number: number;
	/** Ders ekle-bırak: danışman onayına gönderilecek paket için zorunlu taban (çoğunlukla 30). */
	add_drop_akts_min?: number;
	/** Ders ekle-bırak: GNO ≥ 2,50 ise 35, aksi 30 (hazırlıkta farklı olabilir). */
	add_drop_akts_max?: number;
	/** Program yarıyılı için henüz döneme eklenmemiş zorunlular */
	curriculum_mandatory_remaining?: CurriculumMandatoryBrief[];
	/** Seçmeli eklemeden önce listedeki zorunlular tamamlanmalı (zorunlu kapısı açık) */
	curriculum_elective_locked?: boolean;
};

export const getDouStudentRegistrationLimits = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<DouStudentRegistrationLimits>(`/student/me/registration-limits${q}`, token);
};

export const getDouStudentEnrollments = (
	token: string | null,
	termId?: string,
	statuses?: string
) => {
	const params = new URLSearchParams();
	if (termId) params.set('term_id', termId);
	if (statuses) params.set('statuses', statuses);
	const q = params.toString() ? `?${params.toString()}` : '';
	return authFetch<DouEnrollmentsResponse>(`/student/me/enrollments${q}`, token);
};

export const getDouStudentSchedule = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<DouScheduleResponse>(`/student/me/schedule${q}`, token);
};

export const getDouStudentExams = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<{ student_user_id: string; exams: DouExam[]; _mock?: boolean }>(
		`/student/me/exams${q}`,
		token
	);
};

export const getDouStudentGrades = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<DouGradesResponse>(`/student/me/grades${q}`, token);
};

export const getDouStudentGpaSummary = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<DouGpaSummary>(`/student/me/gpa-summary${q}`, token);
};

export const getDouStudentTranscript = (token: string | null) =>
	authFetch<DouTranscriptResponse>('/student/me/transcript', token);

export const getDouStudentAttendance = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<{ student_user_id: string; attendance: DouAttendanceRow[]; _mock?: boolean }>(
		`/student/me/attendance${q}`,
		token
	);
};

export const getDouStudentDocumentRequests = (token: string | null) =>
	authFetch<{ student_user_id: string; requests: DouDocumentRequest[]; _mock?: boolean }>(
		'/student/me/document-requests',
		token
	);

export const createDouDocumentRequest = (
	token: string | null,
	body: {
		requesting_institution: string;
		request_reason: string;
		document_type: string;
		document_subtype: string;
	}
) =>
	authFetch<DouDocumentRequest>('/student/me/document-requests', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const getDouStudentAnnouncements = (token: string | null) =>
	authFetch<{ student_user_id: string; announcements: DouAnnouncement[]; _mock?: boolean }>(
		'/student/me/announcements',
		token
	);

// ---------------------------------------------------------------------------
// Akademisyen
// ---------------------------------------------------------------------------

export const getDouAcademicSections = (
	token: string | null,
	termId?: string,
	opts?: { includeClassrooms?: boolean }
) => {
	const params = new URLSearchParams();
	if (termId) params.set('term_id', termId);
	if (opts?.includeClassrooms) params.set('include_classrooms', 'true');
	const q = params.toString() ? `?${params.toString()}` : '';
	return authFetch<DouAcademicSectionsResponse>(`/academic/me/sections${q}`, token);
};

export const getDouSectionStudents = (token: string | null, sectionId: string) =>
	authFetch<{ section_id: string; section: DouSection; students: unknown[]; _mock?: boolean }>(
		`/academic/me/sections/${sectionId}/students`,
		token
	);

export const getDouAcademicAdvisees = (token: string | null) =>
	authFetch<{ academic_user_id: string; advisees: unknown[]; _mock?: boolean }>(
		'/academic/me/advisees',
		token
	);

export type DouAcademicConsultingHoursResponse = {
	academic_user_id: string;
	consulting_hours: string;
	profile_exists?: boolean;
	_mock?: boolean;
};

/** Danışmanlık sayfasında gösterilen / kaydedilen metin (GET). */
export const getDouAcademicConsultingHours = (token: string | null) =>
	authFetch<DouAcademicConsultingHoursResponse>(
		'/academic/me/consulting-hours',
		token
	);

/** Danışmanlık / görüşme saatleri güncelleme (PUT). Profil satırı yoksa OBS tarafında stub açılabilir. */
export const putDouAcademicConsultingHours = (
	token: string | null,
	consultingHours: string
) =>
	authFetch<DouAcademicConsultingHoursResponse>(
		'/academic/me/consulting-hours',
		token,
		{ method: 'PUT', body: JSON.stringify({ consulting_hours: consultingHours }) }
	);

export const getDouAcademicApprovalRequests = (token: string | null, statusFilter?: string) => {
	const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
	return authFetch<{
		academic_user_id: string;
		requests: DouApprovalRequest[];
		total: number;
		_mock?: boolean;
	}>(`/academic/me/approval-requests${q}`, token);
};

export const resolveDouApprovalRequest = (
	token: string | null,
	requestId: string,
	action: 'approve' | 'reject',
	note?: string
) =>
	authFetch<{ id: string; status: string }>(`/academic/approval-requests/${requestId}`, token, {
		method: 'PATCH',
		body: JSON.stringify({ action, note })
	});

export const getDouAdviseeEnrollments = (
	token: string | null,
	studentUserId: string,
	termId?: string
) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<{
		student_user_id: string;
		term_id: string | null;
		enrollments: DouEnrollment[];
	}>(
		`/academic/me/advisees/${encodeURIComponent(studentUserId)}/enrollments${q}`,
		token
	);
};

export const finalizeDouAdviseeSchedule = (
	token: string | null,
	studentUserId: string,
	termId: string
) =>
	authFetch<{ ok: boolean; student_user_id: string; term_id: string }>(
		'/academic/me/advisees/finalize-schedule',
		token,
		{
			method: 'POST',
			body: JSON.stringify({ student_user_id: studentUserId, term_id: termId })
		}
	);

export const rejectDouAdviseeSchedule = (
	token: string | null,
	studentUserId: string,
	termId: string
) =>
	authFetch<{ ok: boolean; student_user_id: string; term_id: string }>(
		'/academic/me/advisees/reject-schedule',
		token,
		{
			method: 'POST',
			body: JSON.stringify({ student_user_id: studentUserId, term_id: termId })
		}
	);

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export const getDouAdminStats = (token: string | null) =>
	authFetch<DouAdminStats>('/admin/stats', token);

export const getDouAdminDepartments = (token: string | null) =>
	authFetch<DouDepartment[]>('/admin/departments', token);

export const createDouAdminDepartment = (
	token: string | null,
	body: { code: string; name: string }
) =>
	authFetch<DouDepartment>('/admin/departments', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const updateDouAdminDepartment = (
	token: string | null,
	id: string,
	body: { code?: string; name?: string; faculty_name?: string | null }
) =>
	authFetch<DouDepartment>(`/admin/departments/${encodeURIComponent(id)}`, token, {
		method: 'PUT',
		body: JSON.stringify(body)
	});

export const deleteDouAdminDepartment = (token: string | null, id: string) =>
	authFetch<{ deleted: boolean }>(`/admin/departments/${encodeURIComponent(id)}`, token, {
		method: 'DELETE'
	});

export const getDouAdminTerms = (token: string | null) =>
	authFetch<DouTerm[]>('/admin/terms', token);

export const createDouAdminTerm = (token: string | null, body: Partial<DouTerm>) =>
	authFetch<DouTerm>('/admin/terms', token, { method: 'POST', body: JSON.stringify(body) });

export const updateDouAdminTerm = (
	token: string | null,
	id: string,
	body: Partial<{
		name: string;
		starts_at: string;
		ends_at: string;
		start_date: string;
		end_date: string;
		is_active: boolean;
	}>
) =>
	authFetch<DouTerm>(`/admin/terms/${encodeURIComponent(id)}`, token, {
		method: 'PUT',
		body: JSON.stringify(body)
	});

export const deleteDouAdminTerm = (token: string | null, id: string) =>
	authFetch<{ deleted: boolean }>(`/admin/terms/${encodeURIComponent(id)}`, token, {
		method: 'DELETE'
	});

export const patchDouAdminTermRegistrationWindows = (
	token: string | null,
	termId: string,
	body: {
		registration_open?: boolean;
		registration_start?: string;
		registration_end?: string;
		add_drop_open?: boolean;
		add_drop_start?: string;
		add_drop_end?: string;
	}
) =>
	authFetch<DouTerm>(`/admin/terms/${encodeURIComponent(termId)}/registration-windows`, token, {
		method: 'PATCH',
		body: JSON.stringify(body)
	});

export const getDouAdminCourses = (token: string | null) =>
	authFetch<unknown[]>('/admin/courses', token);

export const getDouAdminClassrooms = (token: string | null) =>
	authFetch<unknown[]>('/admin/classrooms', token);

export const getDouAdminSections = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<unknown[]>(`/admin/course-sections${q}`, token);
};

export const updateDouAdminCourse = (
	token: string | null,
	courseId: string,
	body: Record<string, unknown>
) =>
	authFetch<unknown>(`/admin/courses/${encodeURIComponent(courseId)}`, token, {
		method: 'PUT',
		body: JSON.stringify(body)
	});

export const deleteDouAdminCourse = (token: string | null, courseId: string) =>
	authFetch<{ deleted: boolean }>(`/admin/courses/${encodeURIComponent(courseId)}`, token, {
		method: 'DELETE'
	});

export const updateDouAdminClassroom = (
	token: string | null,
	classroomId: string,
	body: Record<string, unknown>
) =>
	authFetch<unknown>(`/admin/classrooms/${encodeURIComponent(classroomId)}`, token, {
		method: 'PUT',
		body: JSON.stringify(body)
	});

export const deleteDouAdminClassroom = (token: string | null, classroomId: string) =>
	authFetch<{ deleted: boolean }>(
		`/admin/classrooms/${encodeURIComponent(classroomId)}`,
		token,
		{ method: 'DELETE' }
	);

export const getDouAdminCalendarEvents = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<DouCalendarEvent[]>(`/admin/calendar-events${q}`, token);
};

export const updateDouAdminCalendarEvent = (
	token: string | null,
	eventId: string,
	body: Partial<{
		term_id: string;
		event_type: string;
		title: string;
		start_date: string;
		end_date: string;
	}>
) =>
	authFetch<Record<string, unknown>>(
		`/admin/calendar/${encodeURIComponent(eventId)}`,
		token,
		{ method: 'PUT', body: JSON.stringify(body) }
	);

export const deleteDouAdminCalendarEvent = (token: string | null, eventId: string) =>
	authFetch<{ deleted: boolean }>(
		`/admin/calendar/${encodeURIComponent(eventId)}`,
		token,
		{ method: 'DELETE' }
	);

export const getDouAdminRegistrationSettings = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<unknown>(`/admin/registration-settings${q}`, token);
};

export const postDouAdminRegistrationSettings = (
	token: string | null,
	body: {
		akts_limit_default?: number;
		akts_limit_high?: number;
		akts_limit_top?: number;
		akts_limit_prep?: number;
		min_gpa_for_high_akts?: number;
		min_gpa_for_top_akts?: number;
		max_akts?: number;
		bonus_akts?: number;
		gpa_threshold?: number;
	},
	termId?: string
) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<unknown>(`/admin/registration-settings${q}`, token, {
		method: 'POST',
		body: JSON.stringify(body)
	});
};

export const createDouAdminAnnouncement = (
	token: string | null,
	body: { title: string; content: string; audience_type?: string; department_id?: string | null }
) =>
	authFetch<{ id: string }>('/admin/announcements', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const getDouAdminAnnouncements = (token: string | null) =>
	authFetch<{ announcements: DouAnnouncement[] }>('/admin/announcements', token);

export type AnnouncementUpdatePayload = Partial<{
	title: string;
	content: string;
	audience_type: string;
	department_id: string | null;
	course_section_id: string | null;
	student_no: string | null;
	is_active: boolean;
}>;

export const updateDouAdminAnnouncement = (
	token: string | null,
	id: string,
	body: AnnouncementUpdatePayload
) =>
	authFetch<DouAnnouncement>(`/admin/announcements/${encodeURIComponent(id)}`, token, {
		method: 'PUT',
		body: JSON.stringify(body)
	});

export const deleteDouAdminAnnouncement = (token: string | null, id: string) =>
	authFetch<{ id: string; deleted: boolean }>(
		`/admin/announcements/${encodeURIComponent(id)}`,
		token,
		{ method: 'DELETE' }
	);

export const getDouAdminAuditLogs = (token: string | null, limit = 200) =>
	authFetch<{ logs: unknown[]; total: number }>(`/admin/audit-logs?limit=${limit}`, token);

export type DouClientAuditPayload = {
	action: string;
	entity_type?: string | null;
	entity_id?: string | null;
	label?: string | null;
	path?: string | null;
	details?: Record<string, unknown> | null;
};

/** Navigasyon / arayüz olayları (`source=client`). */
export const postDouClientAuditEvent = (token: string | null, body: DouClientAuditPayload) =>
	authFetch<object>('/audit/event', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const getDouAdminDocumentRequests = (token: string | null, statusFilter?: string) => {
	const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
	return authFetch<{ requests: DouDocumentRequest[]; total: number }>(
		`/admin/document-requests${q}`,
		token
	);
};

// ---------------------------------------------------------------------------
// Mezuniyet / Harç / Müfredat / Yapılacaklar
// ---------------------------------------------------------------------------

export type DouGraduationRequirement = {
	category: string;
	completed: number;
	required: number;
	akts_completed: number;
	akts_required: number;
	met: boolean;
};
export type DouGraduationApprovalStep = {
	step: string;
	status: 'pending' | 'approved' | 'rejected';
	updated_at: string | null;
};
export type DouGraduationStatus = {
	student_user_id: string;
	cumulative_gpa: number;
	total_akts_completed: number;
	total_akts_required: number;
	total_credits_completed: number;
	total_credits_required: number;
	status: string;
	status_label: string;
	eligible_for_graduation: boolean;
	missing_akts: number;
	missing_credits: number;
	requirements: DouGraduationRequirement[];
	approval_steps: DouGraduationApprovalStep[];
	_mock?: boolean;
};

export type DouFinancialTerm = {
	term_name: string;
	tuition_fee: number;
	amount_paid: number;
	balance: number;
	payment_status: string;
	due_date: string;
	paid_at: string | null;
	receipt_no: string | null;
};
export type DouScholarship = { name: string; amount: number; period: string; status: string };
export type DouFinancialInfo = {
	student_user_id: string;
	is_financially_eligible: boolean;
	academic_year: string;
	terms: DouFinancialTerm[];
	scholarships: DouScholarship[];
	total_paid: number;
	total_scholarship: number;
	_mock?: boolean;
};

export type DouCurriculumCourse = {
	code: string;
	name: string;
	akts: number;
	status: 'tamamlandi' | 'devam_ediyor' | 'alinmadi';
	grade: string | null;
};
export type DouCurriculumCategory = { name: string; courses: DouCurriculumCourse[] };
export type DouCurriculumStatus = {
	student_user_id: string;
	program: string;
	catalog_year: string;
	overall_progress_pct: number;
	categories: DouCurriculumCategory[];
	_mock?: boolean;
};

export type DouTodoItem = {
	id: string;
	title: string;
	category: string;
	due_date: string;
	is_done: boolean;
	priority: 'urgent' | 'high' | 'medium' | 'low';
};
export type DouTodoList = { student_user_id: string; todos: DouTodoItem[]; _mock?: boolean };

export type DouApplication = {
	id: string;
	application_type: string;
	status: string;
	submitted_at: string;
	course_code?: string;
	notes?: string;
	reviewed_by?: string | null;
	reviewed_at?: string | null;
};
export type DouApplicationsResponse = {
	student_user_id: string;
	applications: DouApplication[];
	_mock?: boolean;
};

export type DouInternship = {
	id: string;
	company_name: string;
	company_address: string;
	supervisor_name: string;
	supervisor_email: string;
	start_date: string;
	end_date: string;
	internship_type: string;
	status: string;
	submitted_at: string;
	notes?: string;
};
export type DouInternshipsResponse = {
	student_user_id: string;
	internships: DouInternship[];
	_mock?: boolean;
};

export type DouCreditTransfer = {
	id: string;
	source_institution: string;
	source_course_code: string;
	source_course_name: string;
	source_credits: number;
	target_course_code: string;
	target_course_name: string;
	status: string;
	submitted_at: string;
	notes?: string;
};
export type DouCreditTransfersResponse = {
	student_user_id: string;
	transfers: DouCreditTransfer[];
	_mock?: boolean;
};

export type DouPrepScheduleRow = {
	day: string;
	start: string;
	end: string;
	course_code: string;
	course_name: string;
	classroom: string;
	instructor: string;
};
export type DouPrepExam = {
	course_code: string;
	course_name: string;
	exam_type: string;
	exam_date: string;
	exam_time: string;
	classroom: string;
	weight_percent: number;
};
export type DouPrepGrade = {
	course_code: string;
	course_name: string;
	midterm: number | null;
	final: number | null;
	letter_grade: string | null;
	is_published: boolean;
	is_finalized: boolean;
};
export type DouPrepAttendanceRow = {
	course_code: string;
	course_name: string;
	total_weeks: number;
	absent_count: number;
	attendance_pct: number;
	status: string;
};

export const getDouGraduationStatus = (token: string | null) =>
	authFetch<DouGraduationStatus>('/student/me/graduation-status', token);

export const getDouFinancialInfo = (token: string | null) =>
	authFetch<DouFinancialInfo>('/student/me/financial', token);

export const getDouCurriculumStatus = (token: string | null) =>
	authFetch<DouCurriculumStatus>('/student/me/curriculum-status', token);

export const getDouTodoList = (token: string | null) =>
	authFetch<DouTodoList>('/student/me/todo-list', token);

export const getDouApplications = (token: string | null, applicationType?: string) => {
	const q = applicationType ? `?application_type=${encodeURIComponent(applicationType)}` : '';
	return authFetch<DouApplicationsResponse>(`/student/me/applications${q}`, token);
};

export const createDouApplication = (
	token: string | null,
	body: {
		application_type: string;
		term_id?: string;
		course_code?: string;
		notes?: string;
		extra?: Record<string, unknown>;
	}
) =>
	authFetch<DouApplication>('/student/me/applications', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const getDouPrepSchedule = (token: string | null) =>
	authFetch<{ student_user_id: string; schedule: DouPrepScheduleRow[]; _mock?: boolean }>(
		'/student/me/prep/schedule',
		token
	);

export const getDouPrepExams = (token: string | null) =>
	authFetch<{ student_user_id: string; exams: DouPrepExam[]; _mock?: boolean }>(
		'/student/me/prep/exams',
		token
	);

export const getDouPrepGrades = (token: string | null) =>
	authFetch<{ student_user_id: string; grades: DouPrepGrade[]; _mock?: boolean }>(
		'/student/me/prep/grades',
		token
	);

export const getDouPrepAttendance = (token: string | null) =>
	authFetch<{ student_user_id: string; attendance: DouPrepAttendanceRow[]; _mock?: boolean }>(
		'/student/me/prep/attendance',
		token
	);

export const getDouInternships = (token: string | null) =>
	authFetch<DouInternshipsResponse>('/student/me/internship', token);

export const createDouInternship = (
	token: string | null,
	body: {
		company_name: string;
		company_address: string;
		supervisor_name: string;
		supervisor_email: string;
		start_date: string;
		end_date: string;
		internship_type?: string;
		notes?: string;
	}
) =>
	authFetch<DouInternship>('/student/me/internship', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const getDouCreditTransfers = (token: string | null) =>
	authFetch<DouCreditTransfersResponse>('/student/me/credit-transfer', token);

export const createDouCreditTransfer = (
	token: string | null,
	body: {
		source_institution: string;
		source_course_code: string;
		source_course_name: string;
		source_credits: number;
		target_course_code: string;
		target_course_name: string;
		notes?: string;
	}
) =>
	authFetch<DouCreditTransfer>('/student/me/credit-transfer', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

// ---------------------------------------------------------------------------
// Öğrenci profil düzenleme
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Ek tip alias'ları (admin sayfaları için)
// ---------------------------------------------------------------------------
export type DouCourse = {
	id: string;
	code: string;
	name: string;
	credits: number;
	akts: number;
	department_id?: string;
};
export type DouClassroom = {
	id: string;
	code: string;
	name: string;
	capacity: number;
	building?: string;
	floor?: number;
};

// Admin kısa isim alias'ları
export const getDouCourses = (t: string | null) => getDouAdminCourses(t);
export const getDouClassrooms = (t: string | null) => getDouAdminClassrooms(t);
export const createDouDepartment = (t: string | null, body: { code: string; name: string }) =>
	createDouAdminDepartment(t, body);
export const updateDouDepartment = (
	t: string | null,
	id: string,
	body: { code?: string; name?: string; faculty_name?: string | null }
) => updateDouAdminDepartment(t, id, body);
export const deleteDouDepartment = (t: string | null, id: string) => deleteDouAdminDepartment(t, id);
export const createDouTerm = (t: string | null, body: Partial<DouTerm>) =>
	createDouAdminTerm(t, body);
export const updateDouTerm = (
	t: string | null,
	id: string,
	body: Partial<{
		name: string;
		starts_at: string;
		ends_at: string;
		start_date: string;
		end_date: string;
		is_active: boolean;
	}>
) => updateDouAdminTerm(t, id, body);
export const deleteDouTerm = (t: string | null, id: string) => deleteDouAdminTerm(t, id);
export const createDouCourse = (
	token: string | null,
	body: { code: string; name: string; credits?: number; akts?: number; department_id?: string }
) => authFetch<DouCourse>('/admin/courses', token, { method: 'POST', body: JSON.stringify(body) });
export const updateDouCourse = (token: string | null, id: string, body: Record<string, unknown>) =>
	updateDouAdminCourse(token, id, body);
export const deleteDouCourse = (token: string | null, id: string) => deleteDouAdminCourse(token, id);
export const createDouClassroom = (
	token: string | null,
	body: { code: string; name: string; capacity?: number; building?: string; floor?: number }
) =>
	authFetch<DouClassroom>('/admin/classrooms', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});
export const updateDouClassroom = (token: string | null, id: string, body: Record<string, unknown>) =>
	updateDouAdminClassroom(token, id, body);
export const deleteDouClassroom = (token: string | null, id: string) => deleteDouAdminClassroom(token, id);
export const completeDouDocumentRequest = (token: string | null, requestId: string) =>
	authFetch<{ id: string; status: string }>(`/admin/document-requests/${requestId}`, token, {
		method: 'PATCH',
		body: '{}'
	});

export const updateDouStudentProfile = (
	token: string | null,
	body: {
		full_name?: string;
		phone?: string;
		address?: string;
		emergency_contact?: string;
		emergency_phone?: string;
	}
) =>
	authFetch<{
		user_id: string;
		full_name: string;
		phone: string;
		address: string;
		_mock?: boolean;
	}>('/student/me/profile', token, { method: 'PUT', body: JSON.stringify(body) });

export type AvailableCourse = {
	id: string;
	course_id?: string;
	course_code: string;
	course_name: string;
	credits: number;
	akts: number;
	instructor_name: string;
	day_of_week: string;
	start_time: string;
	end_time: string;
	classroom: string;
	capacity: number;
	enrolled: number;
	registration_priority_tier?: number;
	registration_priority_label?: string;
	/** obs_courses.type (zorunlu, teknik_secmeli vb.) */
	type?: string;
	/** Müfredatta zorunlu mu (type / is_mandatory birleşik). */
	is_mandatory_course?: boolean;
	/** obs_courses.curriculum_semester (müfredat yarıyılı indeksi). */
	curriculum_semester?: number | null;
	/** Tablo için: «4. sınıf» (API: catalog_class_label). */
	catalog_class_label?: string;
	/** Tablo için: Güz / Bahar (API: catalog_half_label). */
	catalog_half_label?: string;
	/** Ekle-bırak: seçilen süre için obs_course_sections satırı yok; seçim yapılamaz. */
	offer_placeholder?: boolean;
};

export const getDouAvailableCourses = (
	token: string | null,
	termId?: string,
	opts?: { forAddDrop?: boolean }
) => {
	const params = new URLSearchParams();
	if (termId) params.set('term_id', termId);
	if (opts?.forAddDrop) params.set('for_add_drop', 'true');
	const q = params.toString() ? `?${params}` : '';
	return authFetch<DouAvailableCoursesResponse>(`/student/available-courses${q}`, token);
};

export type CoursesPendingSectionsBrief = {
	course_id: string;
	course_code?: string;
	course_name?: string;
	akts?: number;
	curriculum_semester?: number | null;
};

export type DouAvailableCoursesResponse = {
	term_id: string | null;
	sections: AvailableCourse[];
	program_semester_number?: number;
	department_id?: string;
	/** Bölüm + program yarıyılı filtresi uygulanıyor mu */
	curriculum_filter_active?: boolean;
	/** Süre öbeğinde toplam `obs_course_sections` satırı (öğrenci filtresi yok). */
	sections_in_terms_total?: number;
	/** Şube seçme sorgusundan sonra kalan uygun şube satırı (aynı süre grubunda bloklar dahil). */
	sections_query_rows_student?: number;
	/** Ekle-bırak: müfredatta eksik zorunlu ama seçilen sürede şube çıkmayan kodlar. */
	courses_pending_sections?: CoursesPendingSectionsBrief[];
	/** Ekle-bırak: liste bomboşken kısa açıklama (müfredat vs şube kaynağı ayrımı). */
	add_drop_sections_empty_hint?: string;
	/** Ders kayıt: aynı mantık için ipucu / teşhis (sepet ekle-bıraktan ayrı metin). */
	registration_sections_empty_hint?: string;
	/** Büyük LISTE sorgusu sonrası gerçek şube satırı. */
	real_section_rows_emitted?: number;
	/** Yer tutucu (şubesiz gösterilen) satır sayısı. */
	offer_placeholder_rows?: number;
	_mock?: boolean;
};

export const createDouEnrollmentRequest = (
	token: string | null,
	sectionIds: string[],
	note?: string
) =>
	authFetch<{ requests: unknown[]; count: number; _mock?: boolean }>(
		'/student/me/enrollment-requests',
		token,
		{ method: 'POST', body: JSON.stringify({ section_ids: sectionIds, note }) }
	);

export const postDouDraftEnrollments = (
	token: string | null,
	sectionIds: string[],
	mode: 'registration' | 'add_drop' = 'registration',
	opts?: { exclude_drop_enrollment_ids?: string[] }
) =>
	authFetch<{ created: unknown[]; count: number }>('/student/me/draft-enrollments', token, {
		method: 'POST',
		body: JSON.stringify({
			section_ids: sectionIds,
			mode,
			exclude_drop_enrollment_ids: opts?.exclude_drop_enrollment_ids ?? []
		})
	});

export const deleteDouDraftEnrollment = (token: string | null, enrollmentId: string) =>
	authFetch<{ id: string; deleted: boolean }>(
		`/student/me/draft-enrollments/${encodeURIComponent(enrollmentId)}`,
		token,
		{ method: 'DELETE' }
	);

export const submitDouStudentSchedule = (
	token: string | null,
	note?: string | null,
	opts?: { flow?: 'registration' | 'add_drop'; enrollment_ids_to_drop?: string[] }
) =>
	authFetch<{ batch_request_id: string; term_id: string; status: string; flow?: string }>(
		'/student/me/submit-schedule',
		token,
		{
			method: 'POST',
			body: JSON.stringify({
				note: note ?? null,
				flow: opts?.flow ?? 'registration',
				enrollment_ids_to_drop: opts?.enrollment_ids_to_drop ?? []
			})
		}
	);

export const createDouDropRequest = (token: string | null, enrollmentId: string, reason?: string) =>
	authFetch<{ id: string; status: string; _mock?: boolean }>('/student/me/drop-requests', token, {
		method: 'POST',
		body: JSON.stringify({ enrollment_id: enrollmentId, reason })
	});

export const sendDouMessageApi = (
	token: string | null,
	body: {
		receiver_user_id?: string;
		receiver_name?: string;
		receiver_type?: string;
		subject: string;
		body: string;
	}
) => authFetch<DouMessage>('/messages', token, { method: 'POST', body: JSON.stringify(body) });

// ---------------------------------------------------------------------------
// Akademisyen — not girişi, yoklama, sınav
// ---------------------------------------------------------------------------

export type AcademicStudent = {
	student_no: string;
	name: string;
	/** Şube öğrencisi mesaj / seçim için WebUI kullanıcı kimliği */
	student_user_id?: string;
	enrollment_id: string;
	enrollment_status: string;
	gpa: number;
};
export type AcademicGradeRow = {
	student_no: string;
	name: string;
	enrollment_id: string;
	midterm: number | null;
	final: number | null;
	makeup: number | null;
	letter_grade: string | null;
	is_finalized: boolean;
};
export type AcademicExam = {
	id: string;
	course_section_id: string;
	exam_type: string;
	exam_date: string;
	exam_time: string;
	classroom: string;
	weight_percent: number;
};

export const getDouAcademicClassrooms = (token: string | null) =>
	authFetch<{ classrooms: DouClassroomOption[] }>('/academic/me/classrooms', token);

export const getDouSectionGrades = (token: string | null, sectionId: string) =>
	authFetch<{
		section_id: string;
		section?: DouSection | null;
		students: AcademicGradeRow[];
		_mock?: boolean;
	}>(`/academic/sections/${encodeURIComponent(sectionId)}/grades`, token);

export const putDouSectionGrades = (
	token: string | null,
	sectionId: string,
	grades: {
		enrollment_id: string;
		midterm?: number;
		final?: number;
		makeup?: number;
		/** Boş string veya null: harf notunu sil (PUT gövdesinde alan varsa) */
		letter_grade?: string | null;
	}[]
) =>
	authFetch<{ section_id: string; updated: number }>(
		`/academic/sections/${encodeURIComponent(sectionId)}/grades`,
		token,
		{ method: 'PUT', body: JSON.stringify({ grades }) }
	);

export const deleteDouSectionGrade = (
	token: string | null,
	sectionId: string,
	enrollmentId: string
) =>
	authFetch<{ section_id: string; enrollment_id: string; deleted: boolean }>(
		`/academic/sections/${encodeURIComponent(sectionId)}/grades/${encodeURIComponent(enrollmentId)}`,
		token,
		{ method: 'DELETE' }
	);

export const finalizeDouSectionGrades = (token: string | null, sectionId: string) =>
	authFetch<{ section_id: string; finalized: boolean }>(
		`/academic/sections/${encodeURIComponent(sectionId)}/grades/finalize`,
		token,
		{ method: 'POST', body: '{}' }
	);

export const putDouSectionGradeWeights = (
	token: string | null,
	sectionId: string,
	body: { midterm_weight_percent: number; final_weight_percent: number }
) =>
	authFetch<{ section_id: string; section?: DouSection | null }>(
		`/academic/sections/${encodeURIComponent(sectionId)}/grade-weights`,
		token,
		{ method: 'PUT', body: JSON.stringify(body) }
	);

export const unfinalizeDouSectionGrade = (
	token: string | null,
	sectionId: string,
	enrollmentId: string
) =>
	authFetch<{ section_id: string; enrollment_id: string; unfinalized: boolean }>(
		`/academic/sections/${encodeURIComponent(sectionId)}/grades/${encodeURIComponent(enrollmentId)}/unfinalize`,
		token,
		{ method: 'POST', body: '{}' }
	);

export const getDouSectionExams = (token: string | null, sectionId: string) =>
	authFetch<{ section_id: string; exams: AcademicExam[]; _mock?: boolean }>(
		`/academic/sections/${sectionId}/exams`,
		token
	);

export const createDouSectionExam = (
	token: string | null,
	sectionId: string,
	body: {
		exam_type: string;
		exam_date: string;
		exam_time?: string;
		classroom?: string;
		weight_percent?: number;
	}
) =>
	authFetch<AcademicExam>(`/academic/sections/${sectionId}/exams`, token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const updateDouSectionExam = (
	token: string | null,
	sectionId: string,
	examId: string,
	body: {
		exam_type?: string;
		exam_date?: string;
		exam_time?: string;
		classroom?: string | null;
		weight_percent?: number;
	}
) =>
	authFetch<AcademicExam>(
		`/academic/sections/${encodeURIComponent(sectionId)}/exams/${encodeURIComponent(examId)}`,
		token,
		{ method: 'PUT', body: JSON.stringify(body) }
	);

export const deleteDouSectionExam = (token: string | null, sectionId: string, examId: string) =>
	authFetch<{ section_id: string; exam_id: string; deleted: boolean }>(
		`/academic/sections/${encodeURIComponent(sectionId)}/exams/${encodeURIComponent(examId)}`,
		token,
		{ method: 'DELETE' }
	);

export const putDouSectionAttendance = (
	token: string | null,
	sectionId: string,
	week_no: number,
	records: { enrollment_id: string; status: 'present' | 'absent' | 'excused' }[]
) =>
	authFetch<{ section_id: string; week_no: number; recorded: number }>(
		`/academic/sections/${encodeURIComponent(sectionId)}/attendance/${encodeURIComponent(String(week_no))}`,
		token,
		{ method: 'PUT', body: JSON.stringify({ records }) }
	);

export const getDouSectionAttendance = (
	token: string | null,
	sectionId: string,
	week_no: number
) =>
	authFetch<{
		section_id: string;
		week_no: number;
		records: { enrollment_id: string; status: 'present' | 'absent' | 'excused' }[];
	}>(
		`/academic/sections/${encodeURIComponent(sectionId)}/attendance/${encodeURIComponent(String(week_no))}`,
		token
	);

export type AcademicAnnouncementBody = {
	title: string;
	content: string;
	audience_type: 'section' | 'advisees' | 'student' | 'all';
	course_section_id?: string;
	student_no?: string;
	department_id?: string;
};

export const createDouAcademicAnnouncement = (
	token: string | null,
	body: AcademicAnnouncementBody
) =>
	authFetch<Record<string, unknown>>('/academic/announcements', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export const getDouAcademicAnnouncements = (token: string | null) =>
	authFetch<{ announcements: DouAnnouncement[] }>('/academic/announcements', token);

export const updateDouAcademicAnnouncement = (
	token: string | null,
	id: string,
	body: AnnouncementUpdatePayload
) =>
	authFetch<DouAnnouncement>(`/academic/announcements/${encodeURIComponent(id)}`, token, {
		method: 'PUT',
		body: JSON.stringify(body)
	});

export const deleteDouAcademicAnnouncement = (token: string | null, id: string) =>
	authFetch<{ id: string; deleted: boolean }>(
		`/academic/announcements/${encodeURIComponent(id)}`,
		token,
		{ method: 'DELETE' }
	);

export type AdminUser = {
	id: string;
	email: string;
	full_name: string;
	role: string;
	is_active: boolean;
	created_at: string;
};
export type AdminRole = {
	id: string;
	name: string;
	description: string;
	permissions: string[];
};

export const getDouAdminUsers = (
	token: string | null,
	params?: { role?: string; search?: string }
) => {
	const sp = new URLSearchParams();
	if (params?.role) sp.set('role', params.role);
	if (params?.search) sp.set('search', params.search);
	const q = sp.toString();
	return authFetch<{ users: AdminUser[]; total: number; _mock?: boolean }>(
		`/admin/users${q ? `?${q}` : ''}`,
		token
	);
};

/** Open WebUI `user` tablosu — OBS panelleri: user | academician | admin (+ isteğe pending) */
export const DOU_ADMIN_USER_ROLES = ['user', 'academician', 'admin', 'pending'] as const;
export type DouAdminAssignableRole = (typeof DOU_ADMIN_USER_ROLES)[number];

/** POST /admin/users — backend `UserCreate` + `obs_student_profiles` / `obs_academic_profiles` */
export type DouStudentProfileCreateInput = {
	student_number: string;
	department_id: string;
	enrollment_date?: string;
	class_year?: number;
	program?: string;
	gpa?: number;
	completed_akts?: number;
	total_akts_required?: number;
	status?: string;
	is_financially_eligible?: boolean;
	phone?: string;
	address?: string;
	emergency_contact?: string;
	emergency_phone?: string;
	tc_kimlik_no?: string;
	birth_date?: string;
	birth_place?: string;
	nationality?: string;
	mother_name?: string;
	father_name?: string;
	high_school_name?: string;
	high_school_graduation_year?: number;
	program_semester_number?: number;
};

export type DouAcademicProfileCreateInput = {
	department_id: string;
	staff_number?: string;
	title?: string;
	office?: string;
	phone?: string;
	consulting_hours?: string;
};

export type DouAdminCreateUserBody = {
	email: string;
	full_name: string;
	role?: DouAdminAssignableRole | string;
	password?: string;
	username?: string;
	gender?: string;
	date_of_birth?: string;
	phone?: string;
	student_profile?: DouStudentProfileCreateInput;
	academic_profile?: DouAcademicProfileCreateInput;
};

export const createDouAdminUser = (token: string | null, body: DouAdminCreateUserBody) =>
	authFetch<AdminUser>('/admin/users', token, { method: 'POST', body: JSON.stringify(body) });

/** Mevcut öğrenci hesabına obs_student_profiles kaydı (auths/add ile oluşanlar için) */
export const postDouAdminUserStudentProfile = (
	token: string | null,
	userId: string,
	body: DouStudentProfileCreateInput
) =>
	authFetch<{ ok: boolean; user_id: string; student_profile_id: string }>(
		`/admin/users/${encodeURIComponent(userId)}/student-profile`,
		token,
		{ method: 'POST', body: JSON.stringify(body) }
	);

export const patchDouAdminUser = (
	token: string | null,
	userId: string,
	body: { full_name?: string; role?: string; is_active?: boolean }
) =>
	authFetch<AdminUser>(`/admin/users/${userId}`, token, {
		method: 'PATCH',
		body: JSON.stringify(body)
	});

export const resetDouAdminUserPassword = (token: string | null, userId: string) =>
	authFetch<{ user_id: string; temp_password: string }>(
		`/admin/users/${userId}/reset-password`,
		token,
		{ method: 'POST', body: '{}' }
	);

export const getDouAdminRoles = (token: string | null) =>
	authFetch<{ roles: AdminRole[]; _mock?: boolean }>('/admin/roles', token);

export const putDouAdminRolePermissions = (
	token: string | null,
	roleId: string,
	permissions: string[]
) =>
	authFetch<AdminRole>(`/admin/roles/${roleId}/permissions`, token, {
		method: 'PUT',
		body: JSON.stringify({ permissions })
	});

// ---------------------------------------------------------------------------
// Admin — Şube Açma
// ---------------------------------------------------------------------------
export type AdminInstructor = { id: string; email: string; full_name: string; role: string };

export const getDouAdminInstructors = (token: string | null) =>
	authFetch<AdminInstructor[]>('/admin/instructors', token);

export type SectionCreateBody = {
	course_id: string;
	course_code?: string;
	course_name?: string;
	term_id: string;
	term_name?: string;
	instructor_id?: string;
	instructor_label?: string;
	classroom_id?: string;
	classroom_code?: string;
	section_no?: number;
	day_of_week?: string;
	start_time?: string;
	end_time?: string;
	capacity?: number;
};

export const createDouAdminSection = (token: string | null, body: SectionCreateBody) =>
	authFetch<Record<string, unknown>>('/admin/course-sections', token, {
		method: 'POST',
		body: JSON.stringify(body)
	});

export type SectionUpdateBody = Partial<{
	course_id: string;
	term_id: string;
	section_no: number;
	classroom_id: string;
	instructor_user_id: string;
	day_of_week: string;
	start_time: string;
	end_time: string;
	capacity: number;
}>;

export const updateDouAdminSection = (
	token: string | null,
	sectionId: string,
	body: SectionUpdateBody
) =>
	authFetch<Record<string, unknown>>(
		`/admin/sections/${encodeURIComponent(sectionId)}`,
		token,
		{ method: 'PUT', body: JSON.stringify(body) }
	);

export const deleteDouAdminSection = (token: string | null, sectionId: string) =>
	authFetch<{ deleted: boolean }>(
		`/admin/sections/${encodeURIComponent(sectionId)}`,
		token,
		{ method: 'DELETE' }
	);

// ---------------------------------------------------------------------------
// Admin — Akademisyen listesi (şube öğretim üyesi ataması için obs_academic_profiles)
// ---------------------------------------------------------------------------
export type AdvisorAssignmentInstructorRow = {
	academic_profile_id: string | null;
	user_id: string;
	full_name: string;
	email: string;
	title: string;
	department_id: string | null;
	department_name: string;
	department_code: string;
};

export const getDouAdvisorAssignmentInstructors = (
	token: string | null,
	departmentId?: string | null
) => {
	const q = departmentId?.trim()
		? `?department_id=${encodeURIComponent(departmentId.trim())}`
		: '';
	return authFetch<{ instructors: AdvisorAssignmentInstructorRow[] }>(
		`/admin/advisor-assignments/instructors${q}`,
		token
	);
};

export const updateDouAdminAcademicProfile = (
	token: string | null,
	userId: string,
	body: Partial<{
		staff_number: string;
		title: string;
		department_id: string | null;
		office: string;
		phone: string;
		consulting_hours: string;
	}>
) =>
	authFetch<Record<string, unknown>>(
		`/admin/academics/${encodeURIComponent(userId)}`,
		token,
		{ method: 'PUT', body: JSON.stringify(body) }
	);

// ---------------------------------------------------------------------------
// Admin — Danışman Atama
// ---------------------------------------------------------------------------
export type AdminStudentAdvisorRow = {
	student_profile_id: string | null;
	user_id: string;
	full_name: string;
	email: string;
	student_number: string;
	department_id: string | null;
	department_code: string;
	department_name: string;
	class_year: number;
	program: string;
	gpa: number | null;
	status: string;
	advisor_assignment_id: string | null;
	advisor_profile_id: string | null;
	advisor_user_id: string;
	advisor_full_name: string;
	advisor_email: string;
	advisor_title: string;
	advisor_valid_from: string | null;
	advisor_valid_to: string | null;
};

export const getDouAdminStudentAdvisors = (
	token: string | null,
	params?: {
		search?: string;
		department_id?: string;
		advisor_user_id?: string;
		only_unassigned?: boolean;
	}
) => {
	const sp = new URLSearchParams();
	if (params?.search?.trim()) sp.set('search', params.search.trim());
	if (params?.department_id?.trim()) sp.set('department_id', params.department_id.trim());
	if (params?.advisor_user_id?.trim()) sp.set('advisor_user_id', params.advisor_user_id.trim());
	if (params?.only_unassigned) sp.set('only_unassigned', 'true');
	const q = sp.toString();
	return authFetch<{ students: AdminStudentAdvisorRow[]; total: number }>(
		`/admin/student-advisors${q ? `?${q}` : ''}`,
		token
	);
};

export const putDouAdminStudentAdvisor = (
	token: string | null,
	studentUserId: string,
	advisorUserId: string | null
) =>
	authFetch<{ ok: boolean; student_user_id: string; advisor_user_id: string | null }>(
		`/admin/student-advisors/${encodeURIComponent(studentUserId)}`,
		token,
		{
			method: 'PUT',
			body: JSON.stringify({ advisor_user_id: advisorUserId ?? null })
		}
	);

export const deleteDouAdminStudentAdvisor = (
	token: string | null,
	studentUserId: string
) =>
	authFetch<{ ok: boolean; student_user_id: string; advisor_user_id: null }>(
		`/admin/student-advisors/${encodeURIComponent(studentUserId)}`,
		token,
		{ method: 'DELETE' }
	);

export type AdminStudentAdvisorBulkResult = {
	updated: number;
	failed: { student_user_id: string; error: string }[];
};

export const postDouAdminStudentAdvisorBulk = (
	token: string | null,
	studentUserIds: string[],
	advisorUserId: string | null
) =>
	authFetch<AdminStudentAdvisorBulkResult>('/admin/student-advisors/bulk', token, {
		method: 'POST',
		body: JSON.stringify({
			student_user_ids: studentUserIds,
			advisor_user_id: advisorUserId ?? null
		})
	});

export const deleteDouAdminAcademicProfile = (token: string | null, userId: string) =>
	authFetch<{ deleted: boolean }>(
		`/admin/academics/${encodeURIComponent(userId)}`,
		token,
		{ method: 'DELETE' }
	);

export const updateDouAdminStudentProfile = (
	token: string | null,
	userId: string,
	body: Record<string, unknown>
) =>
	authFetch<Record<string, unknown>>(
		`/admin/students/${encodeURIComponent(userId)}`,
		token,
		{ method: 'PUT', body: JSON.stringify(body) }
	);

export const deleteDouAdminStudentProfile = (token: string | null, userId: string) =>
	authFetch<{ deleted: boolean }>(
		`/admin/students/${encodeURIComponent(userId)}`,
		token,
		{ method: 'DELETE' }
	);

// ---------------------------------------------------------------------------
// DEV helpers
// ---------------------------------------------------------------------------
export type DevAccount = {
	email: string;
	password: string;
	name: string;
	obs_role: string;
	existed: boolean;
};

export const devSeedUsers = (token: string | null) =>
	authFetch<{ accounts: DevAccount[] }>('/dev/seed-users', token, { method: 'POST', body: '{}' });

export const devGetObsRole = (token: string | null) =>
	authFetch<{ obs_role: string; email: string }>('/dev/obs-role', token);

/** [DEV] Oturumdaki öğrencinin obs_course_enrollments + not + yoklama kayıtlarını siler. */
export const devClearMyStudentEnrollments = (token: string | null) =>
	authFetch<{ ok: boolean; deleted_enrollments: number; detail?: string }>(
		'/dev/clear-my-student-enrollments',
		token,
		{ method: 'POST', body: '{}' }
	);
