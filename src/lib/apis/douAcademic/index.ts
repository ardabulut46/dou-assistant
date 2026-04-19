/**
 * OBS Mock API istemcisi — Faz 2–4
 *
 * Tüm çağrılar bellek içi mock backend'e gider (DB yok).
 * Üretime geçişte yalnızca bu dosyadaki endpoint yolları ve tipler güncellenir.
 */

import { WEBUI_API_BASE_URL } from '$lib/constants';

// ---------------------------------------------------------------------------
// Yardımcı
// ---------------------------------------------------------------------------

async function authFetch<T>(
	path: string,
	token: string | null,
	options?: RequestInit
): Promise<T> {
	if (!token) throw new Error('Oturum tokeni yok');

	const res = await fetch(`${WEBUI_API_BASE_URL}${path}`, {
		...options,
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`,
			...(options?.headers ?? {})
		},
		credentials: 'include'
	});

	// Yanıtı önce text olarak oku; JSON parse hatasını yakalamak için
	const text = await res.text();

	let data: unknown;
	try {
		data = JSON.parse(text);
	} catch {
		// HTML veya boş yanıt döndü (örn. 404 sayfası, sunucu yok)
		if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
		throw new Error(`Sunucu JSON döndürmedi (${res.status}). Endpoint: ${path}`);
	}

	if (!res.ok) {
		const detail = (data as { detail?: string })?.detail;
		throw new Error(detail ?? `HTTP ${res.status}: ${res.statusText}`);
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
	gpa?: number;
	status?: string;
	enrollment_date?: string;
	is_financially_eligible?: boolean;
	_mock?: boolean;
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
};

export type DouAdvisorResponse = {
	student_user_id: string;
	advisor: DouAdvisor;
	valid_from?: string;
	valid_to?: string | null;
	_mock?: boolean;
};

export type DouEnrollment = {
	id: string;
	student_id: string;
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
	status: string;
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
	midterm: number | null;
	final: number | null;
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
	terms: Array<{ term_id: string; term_name: string; term_gpa: number | null; akts_completed: number; akts_passed: number }>;
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
};

export type DouAcademicSectionsResponse = {
	academic_user_id: string;
	term_id_filter: string | null;
	sections: DouSection[];
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

export type DouApprovalRequest = {
	id: string;
	student_name: string;
	student_no: string;
	request_type: string;
	related_enrollment_id?: string;
	course_code?: string;
	course_name?: string;
	status: string;
	note?: string | null;
	created_at: string;
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
	is_active: boolean;
	published_at?: string;
	created_by?: string;
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

export const getDouTerms = (token: string | null) =>
	authFetch<DouTerm[]>('/terms', token);

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
	body: { receiver_user_id: string; receiver_name?: string; receiver_type?: string; subject: string; body: string }
) => authFetch<DouMessage>('/messages', token, { method: 'POST', body: JSON.stringify(body) });

export const markDouMessageRead = (token: string | null, messageId: string) =>
	authFetch<{ id: string; is_read: boolean }>(`/messages/${messageId}/read`, token, { method: 'PATCH' });

export const deleteDouMessage = (token: string | null, messageId: string) =>
	authFetch<{ id: string; status: string }>(`/messages/${messageId}`, token, { method: 'DELETE' });

// ---------------------------------------------------------------------------
// Öğrenci
// ---------------------------------------------------------------------------

export const getDouStudentProfile = (token: string | null) =>
	authFetch<DouStudentProfile>('/student/me/profile', token);

export const getDouStudentAdvisor = (token: string | null) =>
	authFetch<DouAdvisorResponse>('/student/me/advisor', token);

export const getDouStudentEnrollments = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
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
	body: { requesting_institution: string; request_reason: string; document_type: string; document_subtype: string }
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

export const getDouAcademicSections = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
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

export const getDouAcademicApprovalRequests = (token: string | null, statusFilter?: string) => {
	const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
	return authFetch<{ academic_user_id: string; requests: DouApprovalRequest[]; total: number; _mock?: boolean }>(
		`/academic/me/approval-requests${q}`,
		token
	);
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

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export const getDouAdminStats = (token: string | null) =>
	authFetch<DouAdminStats>('/admin/stats', token);

export const getDouAdminDepartments = (token: string | null) =>
	authFetch<DouDepartment[]>('/admin/departments', token);

export const createDouAdminDepartment = (token: string | null, body: { code: string; name: string }) =>
	authFetch<DouDepartment>('/admin/departments', token, { method: 'POST', body: JSON.stringify(body) });

export const getDouAdminTerms = (token: string | null) =>
	authFetch<DouTerm[]>('/admin/terms', token);

export const createDouAdminTerm = (token: string | null, body: Partial<DouTerm>) =>
	authFetch<DouTerm>('/admin/terms', token, { method: 'POST', body: JSON.stringify(body) });

export const getDouAdminCourses = (token: string | null) =>
	authFetch<unknown[]>('/admin/courses', token);

export const getDouAdminClassrooms = (token: string | null) =>
	authFetch<unknown[]>('/admin/classrooms', token);

export const getDouAdminSections = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<unknown[]>(`/admin/course-sections${q}`, token);
};

export const getDouAdminCalendarEvents = (token: string | null, termId?: string) => {
	const q = termId ? `?term_id=${encodeURIComponent(termId)}` : '';
	return authFetch<DouCalendarEvent[]>(`/admin/calendar-events${q}`, token);
};

export const getDouAdminRegistrationSettings = (token: string | null) =>
	authFetch<unknown>('/admin/registration-settings', token);

export const getDouAdminAuditLogs = (token: string | null, limit = 20) =>
	authFetch<{ logs: unknown[]; total: number }>(`/admin/audit-logs?limit=${limit}`, token);

export const getDouAdminDocumentRequests = (token: string | null, statusFilter?: string) => {
	const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
	return authFetch<{ requests: DouDocumentRequest[]; total: number }>(`/admin/document-requests${q}`, token);
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
	day: string; start: string; end: string;
	course_code: string; course_name: string;
	classroom: string; instructor: string;
};
export type DouPrepExam = {
	course_code: string; course_name: string;
	exam_type: string; exam_date: string; exam_time: string;
	classroom: string; weight_percent: number;
};
export type DouPrepGrade = {
	course_code: string; course_name: string;
	midterm: number | null; final: number | null;
	letter_grade: string | null; is_published: boolean; is_finalized: boolean;
};
export type DouPrepAttendanceRow = {
	course_code: string; course_name: string;
	total_weeks: number; absent_count: number;
	attendance_pct: number; status: string;
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
	body: { application_type: string; term_id?: string; course_code?: string; notes?: string; extra?: Record<string, unknown> }
) => authFetch<DouApplication>('/student/me/applications', token, { method: 'POST', body: JSON.stringify(body) });

export const getDouPrepSchedule = (token: string | null) =>
	authFetch<{ student_user_id: string; schedule: DouPrepScheduleRow[]; _mock?: boolean }>(
		'/student/me/prep/schedule', token
	);

export const getDouPrepExams = (token: string | null) =>
	authFetch<{ student_user_id: string; exams: DouPrepExam[]; _mock?: boolean }>(
		'/student/me/prep/exams', token
	);

export const getDouPrepGrades = (token: string | null) =>
	authFetch<{ student_user_id: string; grades: DouPrepGrade[]; _mock?: boolean }>(
		'/student/me/prep/grades', token
	);

export const getDouPrepAttendance = (token: string | null) =>
	authFetch<{ student_user_id: string; attendance: DouPrepAttendanceRow[]; _mock?: boolean }>(
		'/student/me/prep/attendance', token
	);

export const getDouInternships = (token: string | null) =>
	authFetch<DouInternshipsResponse>('/student/me/internship', token);

export const createDouInternship = (
	token: string | null,
	body: {
		company_name: string; company_address: string;
		supervisor_name: string; supervisor_email: string;
		start_date: string; end_date: string;
		internship_type?: string; notes?: string;
	}
) => authFetch<DouInternship>('/student/me/internship', token, { method: 'POST', body: JSON.stringify(body) });

export const getDouCreditTransfers = (token: string | null) =>
	authFetch<DouCreditTransfersResponse>('/student/me/credit-transfer', token);

export const createDouCreditTransfer = (
	token: string | null,
	body: {
		source_institution: string; source_course_code: string; source_course_name: string;
		source_credits: number; target_course_code: string; target_course_name: string; notes?: string;
	}
) => authFetch<DouCreditTransfer>('/student/me/credit-transfer', token, { method: 'POST', body: JSON.stringify(body) });
