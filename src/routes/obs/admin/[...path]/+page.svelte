<script lang="ts">
	import { browser } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import { tick } from 'svelte';
	import ObsShell from '$lib/components/obs/ObsShell.svelte';
	import { user } from '$lib/stores';
	import {
		getDouAdminUsers,
		createDouAdminUser,
		postDouAdminUserStudentProfile,
		patchDouAdminUser,
		getDouAdminRoles,
		putDouAdminRolePermissions,
		getDouDepartments,
		createDouDepartment,
		updateDouDepartment,
		deleteDouDepartment,
		getDouTerms,
		createDouTerm,
		updateDouTerm,
		deleteDouTerm,
		getDouCourses,
		createDouCourse,
		updateDouCourse,
		deleteDouCourse,
		getDouClassrooms,
		createDouClassroom,
		updateDouClassroom,
		deleteDouClassroom,
		getDouAdminDocumentRequests,
		completeDouDocumentRequest,
		getDouAdminAuditLogs,
		getDouAdminInstructors,
		getDouAdminSections,
		createDouAdminSection,
		updateDouAdminSection,
		deleteDouAdminSection,
		updateDouAdminCalendarEvent,
		deleteDouAdminCalendarEvent,
		getDouAdminCalendarEvents,
		getDouAdminRegistrationSettings,
		postDouAdminRegistrationSettings,
		createDouAdminAnnouncement,
		getDouAdminAnnouncements,
		updateDouAdminAnnouncement,
		deleteDouAdminAnnouncement,
		patchDouAdminTermRegistrationWindows,
		getDouAdvisorAssignmentInstructors,
		getDouAdminStudentAdvisors,
		putDouAdminStudentAdvisor,
		deleteDouAdminStudentAdvisor,
		postDouAdminStudentAdvisorBulk,
		type AdminUser,
		type AdminRole,
		type AdminInstructor,
		type DouDepartment,
		type DouTerm,
		type DouCourse,
		type DouClassroom,
		type DouCalendarEvent,
		type DouAnnouncement,
		type DouAdminCreateUserBody,
		type DouStudentProfileCreateInput,
		type AdvisorAssignmentInstructorRow,
		type AdminStudentAdvisorRow
	} from '$lib/apis/douAcademic';

	/** `user` tablosu role — API ile aynı stringler (filtre/liste/create uyumu) */
	const ADMIN_USER_ROLE_OPTIONS: { value: string; label: string }[] = [
		{ value: 'user', label: 'Öğrenci' },
		{ value: 'academician', label: 'Akademisyen' },
		{ value: 'admin', label: 'Admin' },
		{ value: 'pending', label: 'Bekleyen' }
	];

	function adminUserRoleLabel(role: string) {
		return ADMIN_USER_ROLE_OPTIONS.find((o) => o.value === role)?.label ?? role;
	}

	type PageMeta = { title: string; apiKey: string };
	const PAGES: Record<string, PageMeta> = {
		'/obs/admin/kullanici-yonetimi': { title: 'Kullanıcı Yönetimi', apiKey: 'users' },
		'/obs/admin/danisman-atama': {
			title: 'Danışman Atama',
			apiKey: 'student-advisors'
		},
		'/obs/admin/danisman-ve-ders-atama': {
			title: 'Şube — Öğretim Üyesi Atama',
			apiKey: 'section-assignments'
		},
		'/obs/admin/rol-yonetimi': { title: 'Rol Yönetimi', apiKey: 'roles' },
		'/obs/admin/bolum-yonetimi': { title: 'Bölüm Yönetimi', apiKey: 'departments' },
		'/obs/admin/donem-yonetimi': { title: 'Dönem Yönetimi', apiKey: 'terms' },
		'/obs/admin/ders-katalogu': { title: 'Ders Kataloğu', apiKey: 'courses' },
		'/obs/admin/sube-acma': { title: 'Şube Açma', apiKey: 'sections' },
		'/obs/admin/derslik-yonetimi': { title: 'Derslik Yönetimi', apiKey: 'classrooms' },
		'/obs/admin/akademik-takvim': { title: 'Akademik Takvim', apiKey: 'calendar' },
		'/obs/admin/kayit-kurallari': { title: 'Kayıt Kuralları', apiKey: 'reg-rules' },
		'/obs/admin/belge-talebi-isleme': { title: 'Belge Talebi İşleme', apiKey: 'doc-process' },
		'/obs/admin/duyuru-global': { title: 'Global Duyuru', apiKey: 'announce' },
		'/obs/admin/audit-kayitlari': { title: 'Audit Kayıtları', apiKey: 'audit' }
	};

	$: activePath = ($page.url.pathname || '/obs/admin').replace(/\/+$/, '') || '/obs/admin';
	$: meta = PAGES[activePath] ?? {
		title: ($page.params.path ?? '').replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
		apiKey: ''
	};
	$: pageTitle = meta.title;
	$: apiKey = meta.apiKey;

	let loading = false;
	let loadErr: string | null = null;

	// users
	let users: AdminUser[] = [];
	let userSearch = '';
	let userRoleFilter = '';
	let showUserModal = false;
	/** WebUI’de oluşmuş öğrenciye sonradan obs_student_profiles */
	let showOzlukModal = false;
	let ozlukErr: string | null = null;
	let ozlukSaving = false;
	let ozlukTarget: AdminUser | null = null;
	let ozlukSp: ReturnType<typeof emptyNewUser>['student_profile'];

	function emptyNewUser() {
		return {
			email: '',
			full_name: '',
			role: 'user',
			password: '',
			username: '',
			gender: '',
			date_of_birth: '',
			phone: '',
			student_profile: {
				student_number: '',
				department_id: '',
				enrollment_date: '',
				class_year: 1,
				program: 'Lisans',
				gpa: 0,
				completed_akts: 0,
				total_akts_required: 240,
				status: 'active',
				is_financially_eligible: true,
				phone: '',
				address: '',
				emergency_contact: '',
				emergency_phone: '',
				tc_kimlik_no: '',
				birth_date: '',
				birth_place: '',
				nationality: '',
				mother_name: '',
				father_name: '',
				high_school_name: '',
				high_school_graduation_year: '' as number | '',
				program_semester_number: 1
			},
			academic_profile: {
				department_id: '',
				staff_number: '',
				title: '',
				office: '',
				phone: ''
			}
		};
	}

	let newUser = emptyNewUser();
	ozlukSp = emptyNewUser().student_profile;
	let userCreating = false;
	/** Kullanıcı oluştur modalı — loadErr sayfa yükleme ile paylaşılmaz (tam sayfa gizlenmesin) */
	let createUserErr: string | null = null;

	// roles
	let roles: AdminRole[] = [];
	let selectedRoleId = '';
	let rolePermissions: string[] = [];
	let rolesSaving = false;
	let rolesSaved = false;
	const ALL_PERMISSIONS = [
		'users.manage',
		'roles.manage',
		'catalog.manage',
		'sections.manage',
		'calendar.manage',
		'audit.read',
		'grades.get',
		'grades.put',
		'attendance.get',
		'attendance.put',
		'enrollments.post',
		'enrollments.approve',
		'messages.get',
		'messages.post',
		'messages.delete',
		'document_requests.get',
		'document_requests.post',
		'document_requests.manage',
		'announcements.get',
		'announcements.post',
		'exams.get',
		'exams.post',
		'auth.change_password'
	];

	// departments / terms / courses / classrooms
	let departments: DouDepartment[] = [];
	let terms: DouTerm[] = [];
	let courses: DouCourse[] = [];
	let classrooms: DouClassroom[] = [];
	let docRequests: unknown[] = [];
	let auditLogs: unknown[] = [];

	let annForm = { title: '', content: '', audience_type: 'all', department_id: '' };
	let annSaved = false;
	let annErr: string | null = null;
	let annPublishing = false;
	let adminAnnouncements: DouAnnouncement[] = [];
	let annEditId = '';
	let annIsActive = true;
	let regRules = {
		akts_limit_default: 30,
		akts_limit_high: 36,
		akts_limit_top: 45,
		akts_limit_prep: 25,
		min_gpa_for_high_akts: 2.5,
		min_gpa_for_top_akts: 3.5,
		registration_open: true,
		add_drop_deadline_days: 14,
		enrollment_deadline: '',
		add_drop_deadline: ''
	};
	let regSaved = false;
	let regRulesTermId = '';
	let showTermCalModal = false;
	let termCalSaved = false;
	let termCalSaving = false;
	let termCalForm = {
		registration_open: true,
		registration_start: '',
		registration_end: '',
		add_drop_open: false,
		add_drop_start: '',
		add_drop_end: ''
	};
	let calendarEvents: DouCalendarEvent[] = [];
	let calendarTermId = '';

	const CAL_EVENT_STYLES = [
		'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200',
		'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200',
		'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
		'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
		'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
		'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200'
	];

	function fmtCalDate(iso: string) {
		if (!iso) return '—';
		const s = iso.length <= 10 ? `${iso}T12:00:00` : iso;
		const d = new Date(s);
		return Number.isNaN(d.getTime())
			? iso
			: d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' });
	}

	function applyRegistrationRow(row: Record<string, unknown>) {
		if (row.akts_limit_default != null)
			regRules.akts_limit_default = Number(row.akts_limit_default);
		else if (row.max_akts != null) regRules.akts_limit_default = Number(row.max_akts);
		if (row.akts_limit_high != null) regRules.akts_limit_high = Number(row.akts_limit_high);
		else if (row.bonus_akts != null) {
			const base =
				row.max_akts != null ? Number(row.max_akts) : regRules.akts_limit_default;
			regRules.akts_limit_high = base + Number(row.bonus_akts);
		}
		if (row.min_gpa_for_high_akts != null)
			regRules.min_gpa_for_high_akts = Number(row.min_gpa_for_high_akts);
		else if (row.gpa_threshold != null)
			regRules.min_gpa_for_high_akts = Number(row.gpa_threshold);
		if (row.akts_limit_top != null) regRules.akts_limit_top = Number(row.akts_limit_top);
		if (row.min_gpa_for_top_akts != null)
			regRules.min_gpa_for_top_akts = Number(row.min_gpa_for_top_akts);
		if (row.akts_limit_prep != null) regRules.akts_limit_prep = Number(row.akts_limit_prep);
		if (row.registration_open != null) regRules.registration_open = Boolean(row.registration_open);
		if (row.add_drop_deadline_days != null)
			regRules.add_drop_deadline_days = Number(row.add_drop_deadline_days);
		if (row.enrollment_deadline != null)
			regRules.enrollment_deadline = String(row.enrollment_deadline).slice(0, 10);
		if (row.add_drop_deadline != null)
			regRules.add_drop_deadline = String(row.add_drop_deadline).slice(0, 10);
	}

	// Generic create forms
	let deptForm = { code: '', name: '' };
	let termForm = {
		name: '',
		academic_year: '2025-2026',
		season: 'spring',
		starts_at: '',
		ends_at: '',
		is_active: false
	};
	let courseForm = { code: '', name: '', credits: 3, akts: 5, department_id: '' };
	let classForm = { code: '', name: '', capacity: 30, building: '', floor: 0 };
	let formSaved: Record<string, boolean> = {};
	let editingDeptId = '';
	let editingTermId = '';
	let editingCourseId = '';
	let editingClassId = '';
	let editingSectionId = '';
	let editingCalEventId = '';
	let calEditForm = { event_type: '', title: '', start_date: '', end_date: '' };

	// Şube açma
	let instructors: AdminInstructor[] = [];
	let adminSections: unknown[] = [];
	let sectionForm = {
		course_id: '',
		term_id: '',
		instructor_id: '',
		classroom_id: '',
		section_no: 1,
		day_of_week: 'Pazartesi',
		start_time: '09:00',
		end_time: '10:50',
		capacity: 40
	};
	let sectionSaving = false;
	let sectionSaved = false;
	let sectionErr: string | null = null;

	/** Şube — öğretim üyesi adayları (danisman-ve-ders-atama) */
	let assignmentInstructorsAll: AdvisorAssignmentInstructorRow[] = [];
	let assignmentTermId = '';
	let assignmentSectionsList: Record<string, unknown>[] = [];
	let sectionInstrSavingId = '';
	let sectionDraft: Record<string, string> = {};

	function syncSectionDraftFromAssignmentSections() {
		sectionDraft = Object.fromEntries(
			assignmentSectionsList.map((sec) => [
				String(sec.id),
				String(sec.instructor_user_id ?? '')
			])
		);
	}

	/** Danışman Atama (danisman-atama) */
	let studentAdvisorsRows: AdminStudentAdvisorRow[] = [];
	let studentAdvisorsAdvisorOptions: AdvisorAssignmentInstructorRow[] = [];
	let studentAdvisorsSearch = '';
	let studentAdvisorsDeptId = '';
	let studentAdvisorsAdvisorFilter = '';
	let studentAdvisorsOnlyUnassigned = false;
	let studentAdvisorsLoading = false;
	let studentAdvisorsErr: string | null = null;
	let studentAdvisorsInfo: string | null = null;
	let studentAdvisorsRowSavingId = '';
	let studentAdvisorsRowDraft: Record<string, string> = {};
	let studentAdvisorsSelected: Record<string, boolean> = {};
	let studentAdvisorsBulkAdvisor = '';
	let studentAdvisorsBulkSaving = false;

	function studentAdvisorsSyncDraftFromRows() {
		studentAdvisorsRowDraft = Object.fromEntries(
			studentAdvisorsRows.map((r) => [r.user_id, r.advisor_user_id ?? ''])
		);
		studentAdvisorsSelected = {};
	}

	$: studentAdvisorsAllSelected =
		studentAdvisorsRows.length > 0 &&
		studentAdvisorsRows.every((r) => studentAdvisorsSelected[r.user_id]);

	$: studentAdvisorsSelectedIds = studentAdvisorsRows
		.filter((r) => studentAdvisorsSelected[r.user_id])
		.map((r) => r.user_id);

	function toggleStudentAdvisorAll(checked: boolean) {
		const next: Record<string, boolean> = {};
		if (checked) for (const r of studentAdvisorsRows) next[r.user_id] = true;
		studentAdvisorsSelected = next;
	}

	function studentAdvisorsAdvisorLabel(ins: AdvisorAssignmentInstructorRow) {
		const name = ins.full_name?.trim() || ins.email || ins.user_id;
		const tcode = ins.department_code ? ` · ${ins.department_code}` : '';
		const ttitle = ins.title ? `${ins.title} ` : '';
		return `${ttitle}${name}${tcode}`.trim();
	}

	async function reloadStudentAdvisorsList() {
		const token = localStorage.token ?? null;
		if (!token) return;
		studentAdvisorsLoading = true;
		studentAdvisorsErr = null;
		try {
			const res = await getDouAdminStudentAdvisors(token, {
				search: studentAdvisorsSearch || undefined,
				department_id: studentAdvisorsDeptId || undefined,
				advisor_user_id: studentAdvisorsAdvisorFilter || undefined,
				only_unassigned: studentAdvisorsOnlyUnassigned || undefined
			});
			studentAdvisorsRows = res.students ?? [];
			studentAdvisorsSyncDraftFromRows();
		} catch (e: unknown) {
			studentAdvisorsErr = e instanceof Error ? e.message : 'Liste yüklenemedi.';
			studentAdvisorsRows = [];
		} finally {
			studentAdvisorsLoading = false;
		}
	}

	async function persistStudentAdvisor(studentUserId: string, advisorUserId: string) {
		const token = localStorage.token ?? null;
		if (!token) return;
		studentAdvisorsErr = null;
		studentAdvisorsInfo = null;
		studentAdvisorsRowSavingId = studentUserId;
		try {
			if (advisorUserId) {
				await putDouAdminStudentAdvisor(token, studentUserId, advisorUserId);
				studentAdvisorsInfo = 'Danışman güncellendi.';
			} else {
				await deleteDouAdminStudentAdvisor(token, studentUserId);
				studentAdvisorsInfo = 'Danışmanlık kaldırıldı.';
			}
			await reloadStudentAdvisorsList();
		} catch (e: unknown) {
			studentAdvisorsErr = e instanceof Error ? e.message : 'Atama yapılamadı.';
		} finally {
			studentAdvisorsRowSavingId = '';
		}
	}

	async function bulkAssignStudentAdvisor() {
		const ids = studentAdvisorsSelectedIds;
		if (!ids.length) {
			studentAdvisorsErr = 'En az bir öğrenci seçin.';
			return;
		}
		const token = localStorage.token ?? null;
		if (!token) return;
		studentAdvisorsErr = null;
		studentAdvisorsInfo = null;
		studentAdvisorsBulkSaving = true;
		try {
			const res = await postDouAdminStudentAdvisorBulk(
				token,
				ids,
				studentAdvisorsBulkAdvisor || null
			);
			studentAdvisorsInfo = `${res.updated} öğrenci güncellendi${res.failed.length ? `, ${res.failed.length} hata` : ''}.`;
			await reloadStudentAdvisorsList();
		} catch (e: unknown) {
			studentAdvisorsErr = e instanceof Error ? e.message : 'Toplu atama yapılamadı.';
		} finally {
			studentAdvisorsBulkSaving = false;
		}
	}

	const DAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];
	const HOURS = [
		'08:00',
		'09:00',
		'10:00',
		'11:00',
		'12:00',
		'13:00',
		'14:00',
		'15:00',
		'16:00',
		'17:00',
		'18:00'
	];

	type TokenFn = (token: string | null) => Promise<unknown>;

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

		const loaders: Record<string, TokenFn> = {
			users: async (t) => {
				const [uRes, dRes] = await Promise.allSettled([
					getDouAdminUsers(t, {
						role: userRoleFilter || undefined,
						search: userSearch || undefined
					}),
					getDouDepartments(t)
				]);
				if (uRes.status === 'fulfilled') users = uRes.value.users;
				if (dRes.status === 'fulfilled') departments = dRes.value;
			},
			roles: (t) =>
				getDouAdminRoles(t).then((r) => {
					roles = r.roles;
					if (!selectedRoleId && roles.length) {
						selectedRoleId = roles[0].id;
						rolePermissions = [...(roles[0].permissions ?? [])];
					}
				}),
			departments: (t) =>
				getDouDepartments(t).then((r) => {
					departments = r;
				}),
			terms: (t) =>
				getDouTerms(t).then((r) => {
					terms = r;
				}),
			courses: async (t) => {
				const [cRes, dRes] = await Promise.allSettled([getDouCourses(t), getDouDepartments(t)]);
				if (cRes.status === 'fulfilled') courses = cRes.value as DouCourse[];
				if (dRes.status === 'fulfilled') departments = dRes.value as DouDepartment[];
			},
			classrooms: (t) =>
				getDouClassrooms(t).then((r) => {
					classrooms = r;
				}),
			sections: async (t) => {
				const [iRes, sRes, cRes, tRes, clRes] = await Promise.allSettled([
					getDouAdminInstructors(t),
					getDouAdminSections(t),
					getDouCourses(t),
					getDouTerms(t),
					getDouClassrooms(t)
				]);
				if (iRes.status === 'fulfilled') instructors = iRes.value as AdminInstructor[];
				else instructors = [];
				if (sRes.status === 'fulfilled') adminSections = sRes.value as unknown[];
				if (cRes.status === 'fulfilled') courses = cRes.value;
				if (tRes.status === 'fulfilled') terms = tRes.value;
				if (clRes.status === 'fulfilled') classrooms = clRes.value;
			},
			calendar: async (t) => {
				const tr = await getDouTerms(t);
				terms = tr;
				const active = tr.find((x) => x.is_active) ?? tr[0];
				calendarTermId = active?.id ?? '';
				calendarEvents = calendarTermId ? await getDouAdminCalendarEvents(t, calendarTermId) : [];
			},
			'reg-rules': async (t) => {
				const tr = await getDouTerms(t);
				terms = tr;
				const active = tr.find((x) => x.is_active) ?? tr[0];
				regRulesTermId = active?.id ?? '';
				const row = await getDouAdminRegistrationSettings(t, regRulesTermId || undefined);
				if (row && typeof row === 'object' && Object.keys(row as object).length) {
					applyRegistrationRow(row as Record<string, unknown>);
				}
			},
			announce: async (t) => {
				annErr = null;
				const [aRes, dRes] = await Promise.allSettled([
					getDouAdminAnnouncements(t),
					getDouDepartments(t)
				]);
				if (aRes.status === 'fulfilled') adminAnnouncements = aRes.value.announcements ?? [];
				else adminAnnouncements = [];
				if (dRes.status === 'fulfilled') departments = dRes.value;
			},
			'doc-process': (t) =>
				getDouAdminDocumentRequests(t).then((r) => {
					docRequests = (r as unknown as { requests: unknown[] }).requests ?? [];
				}),
			audit: (t) =>
				getDouAdminAuditLogs(t).then((r) => {
					auditLogs = (r as unknown as { logs: unknown[] }).logs ?? [];
				}),
			'student-advisors': async (t) => {
				const [dRes, insRes, listRes] = await Promise.allSettled([
					getDouDepartments(t),
					getDouAdvisorAssignmentInstructors(t),
					getDouAdminStudentAdvisors(t, {
						search: studentAdvisorsSearch || undefined,
						department_id: studentAdvisorsDeptId || undefined,
						advisor_user_id: studentAdvisorsAdvisorFilter || undefined,
						only_unassigned: studentAdvisorsOnlyUnassigned || undefined
					})
				]);
				if (dRes.status === 'fulfilled') departments = dRes.value;
				if (insRes.status === 'fulfilled') {
					studentAdvisorsAdvisorOptions = [...(insRes.value.instructors ?? [])];
				}
				if (!studentAdvisorsAdvisorOptions.length) {
					try {
						const ur = await getDouAdminUsers(t, { role: 'academician' });
						studentAdvisorsAdvisorOptions = (ur.users ?? []).map((u) => ({
							academic_profile_id: null,
							user_id: u.id,
							full_name: u.full_name ?? u.email ?? '',
							email: u.email ?? '',
							title: '',
							department_id: null,
							department_name: '',
							department_code: ''
						}));
					} catch {
						/* ignore */
					}
				}
				if (listRes.status === 'fulfilled') {
					studentAdvisorsRows = listRes.value.students ?? [];
				} else {
					studentAdvisorsErr =
						listRes.reason instanceof Error
							? listRes.reason.message
							: 'Liste yüklenemedi.';
					studentAdvisorsRows = [];
				}
				studentAdvisorsSyncDraftFromRows();
			},
			'section-assignments': async (t) => {
				const tr = await getDouTerms(t);
				terms = tr;
				assignmentTermId = tr.find((x) => x.is_active)?.id ?? tr[0]?.id ?? '';
				const [insRes, secRes] = await Promise.allSettled([
					getDouAdvisorAssignmentInstructors(t),
					assignmentTermId ? getDouAdminSections(t, assignmentTermId) : Promise.resolve([])
				]);
				if (insRes.status === 'fulfilled') {
					assignmentInstructorsAll = [...(insRes.value.instructors ?? [])];
				}
				if (!assignmentInstructorsAll.length) {
					try {
						const ur = await getDouAdminUsers(t, { role: 'academician' });
						assignmentInstructorsAll = (ur.users ?? []).map((u) => ({
							academic_profile_id: null,
							user_id: u.id,
							full_name: u.full_name ?? u.email ?? '',
							email: u.email ?? '',
							title: '',
							department_id: null,
							department_name: '',
							department_code: ''
						}));
					} catch {
						/* ignore */
					}
				}
				if (secRes.status === 'fulfilled')
					assignmentSectionsList = secRes.value as unknown as Record<string, unknown>[];
				else assignmentSectionsList = [];
				syncSectionDraftFromAssignmentSections();
			}
		};
		try {
			await (loaders[apiKey]?.(token) ?? Promise.resolve());
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'API hatası.';
		} finally {
			loading = false;
		}
	}

	async function reloadAssignmentSectionsOnly() {
		const token = localStorage.token ?? null;
		if (!token || !assignmentTermId) {
			assignmentSectionsList = [];
			return;
		}
		try {
			const rows = await getDouAdminSections(token, assignmentTermId);
			assignmentSectionsList = rows as unknown as Record<string, unknown>[];
			syncSectionDraftFromAssignmentSections();
		} catch {
			assignmentSectionsList = [];
			sectionDraft = {};
		}
	}

	async function persistSectionInstructor(sectionId: string, instructorUserId: string) {
		const token = localStorage.token ?? null;
		if (!token) return;
		sectionInstrSavingId = sectionId;
		loadErr = null;
		try {
			await updateDouAdminSection(token, sectionId, {
				instructor_user_id: instructorUserId || ''
			});
			await reloadAssignmentSectionsOnly();
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Öğretim üyesi güncellenemedi.';
		} finally {
			sectionInstrSavingId = '';
		}
	}

	function syncTermCalFromSelected() {
		const tm = terms.find((t) => t.id === regRulesTermId);
		if (!tm) return;
		termCalForm = {
			registration_open: tm.registration_open !== false,
			registration_start: tm.registration_start ?? '',
			registration_end: tm.registration_end ?? '',
			add_drop_open: tm.add_drop_open === true,
			add_drop_start: tm.add_drop_start ?? '',
			add_drop_end: tm.add_drop_end ?? ''
		};
	}

	async function saveTermCalWindows() {
		termCalSaving = true;
		termCalSaved = false;
		loadErr = null;
		const token = localStorage.token ?? null;
		if (!token || !regRulesTermId) {
			termCalSaving = false;
			return;
		}
		try {
			await patchDouAdminTermRegistrationWindows(token, regRulesTermId, { ...termCalForm });
			const tr = await getDouTerms(token);
			terms = tr;
			termCalSaved = true;
			showTermCalModal = false;
			setTimeout(() => {
				termCalSaved = false;
			}, 3500);
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Takvim kaydedilemedi.';
		} finally {
			termCalSaving = false;
		}
	}

	async function reloadCalendarEvents() {
		if (!browser) return;
		const token = localStorage.token ?? null;
		if (!token || !calendarTermId) return;
		try {
			calendarEvents = await getDouAdminCalendarEvents(token, calendarTermId);
		} catch {
			/* ignore */
		}
	}

	function calDateInput(iso: string) {
		if (!iso) return '';
		return iso.length > 10 ? iso.slice(0, 10) : iso;
	}

	function startCalEdit(ev: DouCalendarEvent) {
		editingCalEventId = ev.id;
		calEditForm = {
			event_type: ev.event_type ?? '',
			title: ev.title ?? '',
			start_date: calDateInput(ev.start_date),
			end_date: calDateInput(ev.end_date)
		};
	}

	function cancelCalEdit() {
		editingCalEventId = '';
	}

	async function saveCalCatalogEdit() {
		const token = localStorage.token ?? null;
		if (!token || !editingCalEventId) return;
		loadErr = null;
		try {
			await updateDouAdminCalendarEvent(token, editingCalEventId, {
				term_id: calendarTermId,
				event_type: calEditForm.event_type,
				title: calEditForm.title,
				start_date: calEditForm.start_date,
				end_date: calEditForm.end_date
			});
			editingCalEventId = '';
			await reloadCalendarEvents();
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Takvim güncellenemedi.';
		}
	}

	async function removeCalendarEventRow(id: string) {
		if (!browser || !confirm('Bu takvim kaydını silmek istediğinize emin misiniz?')) return;
		const token = localStorage.token ?? null;
		loadErr = null;
		try {
			await deleteDouAdminCalendarEvent(token, id);
			if (editingCalEventId === id) cancelCalEdit();
			await reloadCalendarEvents();
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Silinemedi.';
		}
	}

	async function saveRegRules() {
		regSaved = false;
		const token = localStorage.token ?? null;
		if (!token) return;
		try {
			await postDouAdminRegistrationSettings(
				token,
				{
					akts_limit_default: regRules.akts_limit_default,
					akts_limit_high: regRules.akts_limit_high,
					akts_limit_top: regRules.akts_limit_top,
					akts_limit_prep: regRules.akts_limit_prep,
					min_gpa_for_high_akts: regRules.min_gpa_for_high_akts,
					min_gpa_for_top_akts: regRules.min_gpa_for_top_akts,
					registration_open: regRules.registration_open,
					add_drop_deadline_days: regRules.add_drop_deadline_days,
					enrollment_deadline: regRules.enrollment_deadline || null,
					add_drop_deadline: regRules.add_drop_deadline || null
				},
				regRulesTermId || undefined
			);
			regSaved = true;
			setTimeout(() => {
				regSaved = false;
			}, 3500);
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Kayıt kuralları kaydedilemedi.';
		}
	}

	function cancelAnnEdit() {
		annEditId = '';
		annIsActive = true;
		annForm = { title: '', content: '', audience_type: 'all', department_id: '' };
	}

	function startAnnEdit(a: DouAnnouncement) {
		annErr = null;
		annEditId = a.id;
		const isDept = (a.audience_type || '') === 'department';
		annForm = {
			title: a.title,
			content: a.content,
			audience_type: isDept ? 'department' : 'all',
			department_id: a.department_id ?? ''
		};
		annIsActive = a.is_active !== false;
	}

	async function removeAdminAnn(id: string) {
		if (!browser || !confirm('Bu duyuruyu silmek istediğinize emin misiniz?')) return;
		const token = localStorage.token ?? null;
		annErr = null;
		try {
			await deleteDouAdminAnnouncement(token, id);
			adminAnnouncements = adminAnnouncements.filter((x) => x.id !== id);
			if (annEditId === id) cancelAnnEdit();
		} catch (e: unknown) {
			annErr = e instanceof Error ? e.message : 'Silinemedi.';
		}
	}

	async function publishAnnounce() {
		annErr = null;
		annSaved = false;
		const token = localStorage.token ?? null;
		if (!token || !annForm.title.trim() || !annForm.content.trim()) {
			annErr = 'Başlık ve içerik zorunludur.';
			return;
		}
		if (annForm.audience_type === 'department' && !annForm.department_id) {
			annErr = 'Bölüm duyurusu için bölüm seçin.';
			return;
		}
		annPublishing = true;
		try {
			const aud =
				annForm.audience_type === 'department' && annForm.department_id ? 'department' : 'all';
			const deptId = aud === 'department' ? annForm.department_id || null : null;
			if (annEditId) {
				await updateDouAdminAnnouncement(token, annEditId, {
					title: annForm.title.trim(),
					content: annForm.content.trim(),
					audience_type: aud,
					department_id: deptId,
					is_active: annIsActive
				});
			} else {
				await createDouAdminAnnouncement(token, {
					title: annForm.title.trim(),
					content: annForm.content.trim(),
					audience_type: aud,
					department_id: deptId
				});
			}
			annSaved = true;
			cancelAnnEdit();
			const refreshed = await getDouAdminAnnouncements(token);
			adminAnnouncements = refreshed.announcements ?? [];
			setTimeout(() => {
				annSaved = false;
			}, 4000);
		} catch (e: unknown) {
			annErr = e instanceof Error ? e.message : 'Duyuru gönderilemedi.';
		} finally {
			annPublishing = false;
		}
	}

	afterNavigate(async () => {
		await tick();
		if (!browser) return;
		void loadPage();
	});

	async function createUser() {
		userCreating = true;
		createUserErr = null;
		const token = localStorage.token ?? null;
		if (!token) {
			userCreating = false;
			return;
		}
		if (!newUser.email.trim() || !newUser.full_name.trim() || !newUser.password) {
			createUserErr = 'E-posta, ad soyad ve parola zorunludur.';
			userCreating = false;
			return;
		}
		if (newUser.role === 'user' || newUser.role === 'pending') {
			if (
				!newUser.student_profile.student_number.trim() ||
				!newUser.student_profile.department_id
			) {
				createUserErr = 'Öğrenci / bekleyen için öğrenci numarası ve bölüm seçimi zorunludur.';
				userCreating = false;
				return;
			}
		}
		if (newUser.role === 'academician' && !newUser.academic_profile.department_id) {
			createUserErr = 'Akademisyen için bölüm seçimi zorunludur.';
			userCreating = false;
			return;
		}

		const payload: DouAdminCreateUserBody = {
			email: newUser.email.trim(),
			full_name: newUser.full_name.trim(),
			role: newUser.role,
			password: newUser.password
		};
		if (newUser.username?.trim()) payload.username = newUser.username.trim();
		if (newUser.gender?.trim()) payload.gender = newUser.gender.trim();
		if (newUser.date_of_birth?.trim()) payload.date_of_birth = newUser.date_of_birth.trim();
		if (newUser.phone?.trim()) payload.phone = newUser.phone.trim();

		if (newUser.role === 'user' || newUser.role === 'pending') {
			const sp = newUser.student_profile;
			const hsRaw = sp.high_school_graduation_year;
			const hsNum =
				typeof hsRaw === 'number'
					? hsRaw
					: String(hsRaw ?? '').trim()
						? parseInt(String(hsRaw).trim(), 10)
						: NaN;
			payload.student_profile = {
				student_number: sp.student_number.trim(),
				department_id: sp.department_id,
				enrollment_date: sp.enrollment_date?.trim() || undefined,
				class_year: Number(sp.class_year) || 1,
				program: (sp.program || 'Lisans').trim(),
				gpa: Number(sp.gpa) || 0,
				completed_akts: Number(sp.completed_akts) || 0,
				total_akts_required: Number(sp.total_akts_required) || 240,
				status: sp.status || 'active',
				is_financially_eligible: sp.is_financially_eligible !== false,
				phone: sp.phone?.trim() || undefined,
				address: sp.address?.trim() || undefined,
				emergency_contact: sp.emergency_contact?.trim() || undefined,
				emergency_phone: sp.emergency_phone?.trim() || undefined,
				tc_kimlik_no: sp.tc_kimlik_no?.trim() || undefined,
				birth_date: sp.birth_date?.trim() || undefined,
				birth_place: sp.birth_place?.trim() || undefined,
				nationality: sp.nationality?.trim() || undefined,
				mother_name: sp.mother_name?.trim() || undefined,
				father_name: sp.father_name?.trim() || undefined,
				high_school_name: sp.high_school_name?.trim() || undefined,
				program_semester_number: Number(sp.program_semester_number) || 1
			};
			if (Number.isFinite(hsNum)) payload.student_profile.high_school_graduation_year = hsNum;
		}
		if (newUser.role === 'academician') {
			const ap = newUser.academic_profile;
			payload.academic_profile = {
				department_id: ap.department_id,
				staff_number: ap.staff_number?.trim() || undefined,
				title: ap.title?.trim() || undefined,
				office: ap.office?.trim() || undefined,
				phone: ap.phone?.trim() || undefined
			};
		}

		try {
			await createDouAdminUser(token, payload);
			showUserModal = false;
			createUserErr = null;
			newUser = emptyNewUser();
			const r = await getDouAdminUsers(token, {
				role: userRoleFilter || undefined,
				search: userSearch || undefined
			});
			users = r.users ?? [];
		} catch (e: unknown) {
			createUserErr = e instanceof Error ? e.message : 'Kullanıcı oluşturulamadı.';
		} finally {
			userCreating = false;
		}
	}

	function openOzlukModal(u: AdminUser) {
		if (u.role !== 'user' && u.role !== 'pending') return;
		ozlukTarget = u;
		ozlukSp = { ...emptyNewUser().student_profile };
		ozlukErr = null;
		showOzlukModal = true;
	}

	async function submitOzluk() {
		ozlukSaving = true;
		ozlukErr = null;
		const token = localStorage.token ?? null;
		if (!token || !ozlukTarget) {
			ozlukSaving = false;
			return;
		}
		if (!ozlukSp.student_number?.trim() || !ozlukSp.department_id) {
			ozlukErr = 'Öğrenci numarası ve bölüm seçimi zorunludur.';
			ozlukSaving = false;
			return;
		}
		try {
			const sp = ozlukSp;
			const hsRaw = sp.high_school_graduation_year;
			const hsNum =
				typeof hsRaw === 'number'
					? hsRaw
					: String(hsRaw ?? '').trim()
						? parseInt(String(hsRaw).trim(), 10)
						: NaN;
			const payload: DouStudentProfileCreateInput = {
				student_number: sp.student_number.trim(),
				department_id: sp.department_id,
				enrollment_date: sp.enrollment_date?.trim() || undefined,
				class_year: Number(sp.class_year) || 1,
				program: (sp.program || 'Lisans').trim(),
				gpa: Number(sp.gpa) || 0,
				completed_akts: Number(sp.completed_akts) || 0,
				total_akts_required: Number(sp.total_akts_required) || 240,
				status: sp.status || 'active',
				is_financially_eligible: sp.is_financially_eligible !== false,
				phone: sp.phone?.trim() || undefined,
				address: sp.address?.trim() || undefined,
				emergency_contact: sp.emergency_contact?.trim() || undefined,
				emergency_phone: sp.emergency_phone?.trim() || undefined,
				tc_kimlik_no: sp.tc_kimlik_no?.trim() || undefined,
				birth_date: sp.birth_date?.trim() || undefined,
				birth_place: sp.birth_place?.trim() || undefined,
				nationality: sp.nationality?.trim() || undefined,
				mother_name: sp.mother_name?.trim() || undefined,
				father_name: sp.father_name?.trim() || undefined,
				high_school_name: sp.high_school_name?.trim() || undefined,
				program_semester_number: Number(sp.program_semester_number) || 1
			};
			if (Number.isFinite(hsNum)) payload.high_school_graduation_year = hsNum;

			await postDouAdminUserStudentProfile(token, ozlukTarget.id, payload);
			showOzlukModal = false;
			ozlukTarget = null;
			const r = await getDouAdminUsers(token, {
				role: userRoleFilter || undefined,
				search: userSearch || undefined
			});
			users = r.users ?? [];
		} catch (e: unknown) {
			ozlukErr = e instanceof Error ? e.message : 'Özlük kaydı oluşturulamadı.';
		} finally {
			ozlukSaving = false;
		}
	}

	async function toggleUserActive(u: AdminUser) {
		const token = localStorage.token ?? null;
		const updated = await patchDouAdminUser(token, u.id, { is_active: !u.is_active }).catch(
			() => u
		);
		users = users.map((x) => (x.id === u.id ? updated : x));
	}

	async function changeUserRole(u: AdminUser, role: string) {
		const token = localStorage.token ?? null;
		if (!token) return;
		loadErr = null;
		try {
			await patchDouAdminUser(token, u.id, { role });
			const r = await getDouAdminUsers(token, {
				role: userRoleFilter || undefined,
				search: userSearch || undefined
			});
			users = r.users ?? [];
		} catch {
			loadErr = 'Rol güncellenemedi.';
		}
	}

	async function saveRolePermissions() {
		rolesSaving = true;
		loadErr = null;
		const token = localStorage.token ?? null;
		try {
			await putDouAdminRolePermissions(token, selectedRoleId, rolePermissions);
			rolesSaved = true;
		} catch (e: unknown) {
			rolesSaved = false;
			loadErr = e instanceof Error ? e.message : 'İzinler kaydedilemedi.';
		} finally {
			rolesSaving = false;
		}
	}

	async function createSection() {
		if (!sectionForm.course_id || !sectionForm.term_id || !sectionForm.instructor_id) {
			sectionErr = 'Ders, dönem ve akademisyen seçimi zorunludur.';
			return;
		}
		sectionSaving = true;
		sectionErr = null;
		const token = localStorage.token ?? null;
		const course = courses.find((c) => c.id === sectionForm.course_id);
		const term = terms.find((t) => t.id === sectionForm.term_id);
		const instr = instructors.find((i) => i.id === sectionForm.instructor_id);
		const cls = classrooms.find((c) => c.id === sectionForm.classroom_id);
		try {
			if (editingSectionId) {
				await updateDouAdminSection(token, editingSectionId, {
					course_id: sectionForm.course_id,
					term_id: sectionForm.term_id,
					section_no: sectionForm.section_no,
					classroom_id: sectionForm.classroom_id || undefined,
					instructor_user_id: sectionForm.instructor_id,
					day_of_week: sectionForm.day_of_week,
					start_time: sectionForm.start_time,
					end_time: sectionForm.end_time,
					capacity: sectionForm.capacity
				});
				editingSectionId = '';
			} else {
				const newSec = await createDouAdminSection(token, {
					course_id: sectionForm.course_id,
					course_code: course?.code ?? '',
					course_name: course?.name ?? '',
					term_id: sectionForm.term_id,
					term_name: term?.name ?? '',
					instructor_id: sectionForm.instructor_id,
					instructor_label: instr?.full_name ?? 'Bilinmiyor',
					classroom_id: sectionForm.classroom_id,
					classroom_code: cls?.code ?? '',
					section_no: sectionForm.section_no,
					day_of_week: sectionForm.day_of_week,
					start_time: sectionForm.start_time,
					end_time: sectionForm.end_time,
					capacity: sectionForm.capacity
				});
				adminSections = [...adminSections, newSec];
			}
			sectionSaved = true;
			sectionForm = {
				course_id: '',
				term_id: '',
				instructor_id: '',
				classroom_id: '',
				section_no: 1,
				day_of_week: 'Pazartesi',
				start_time: '09:00',
				end_time: '10:50',
				capacity: 40
			};
			editingSectionId = '';
			await loadPage();
			setTimeout(() => (sectionSaved = false), 3500);
		} catch (e: unknown) {
			sectionErr = e instanceof Error ? e.message : 'Şube oluşturulamadı.';
		} finally {
			sectionSaving = false;
		}
	}

	function resetSectionForm() {
		sectionForm = {
			course_id: '',
			term_id: '',
			instructor_id: '',
			classroom_id: '',
			section_no: 1,
			day_of_week: 'Pazartesi',
			start_time: '09:00',
			end_time: '10:50',
			capacity: 40
		};
	}

	function startSectionEdit(sec: Record<string, unknown>) {
		editingSectionId = String(sec.id ?? '');
		sectionForm = {
			course_id: String(sec.course_id ?? ''),
			term_id: String(sec.term_id ?? ''),
			instructor_id: String(sec.instructor_user_id ?? ''),
			classroom_id: String(sec.classroom_id ?? ''),
			section_no: Number(sec.section_no ?? 1),
			day_of_week: String(sec.day_of_week ?? 'Pazartesi'),
			start_time: String(sec.start_time ?? '09:00').slice(0, 5),
			end_time: String(sec.end_time ?? '10:50').slice(0, 5),
			capacity: Number(sec.capacity ?? 40)
		};
		sectionErr = null;
	}

	function cancelSectionEdit() {
		editingSectionId = '';
		resetSectionForm();
	}

	async function removeSectionRow(id: string) {
		if (!browser || !confirm('Bu şubeyi silmek istediğinize emin misiniz?')) return;
		const token = localStorage.token ?? null;
		sectionErr = null;
		try {
			await deleteDouAdminSection(token, id);
			if (editingSectionId === id) cancelSectionEdit();
			await loadPage();
		} catch (e: unknown) {
			sectionErr = e instanceof Error ? e.message : 'Şube silinemedi.';
		}
	}

	async function completeDoc(id: string) {
		const token = localStorage.token ?? null;
		loadErr = null;
		try {
			await completeDouDocumentRequest(token, id);
			docRequests = (docRequests as { id: string; status: string }[]).map((r) =>
				r.id === id ? { ...r, status: 'tamamlandı' } : r
			);
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Belge talebi güncellenemedi.';
		}
	}

	function cancelCatalogEdits(formType: string) {
		if (formType === 'dept') {
			editingDeptId = '';
			deptForm = { code: '', name: '' };
		}
		if (formType === 'term') {
			editingTermId = '';
			termForm = {
				name: '',
				academic_year: '2025-2026',
				season: 'spring',
				starts_at: '',
				ends_at: '',
				is_active: false
			};
		}
		if (formType === 'course') {
			editingCourseId = '';
			courseForm = { code: '', name: '', credits: 3, akts: 5, department_id: '' };
		}
		if (formType === 'class') {
			editingClassId = '';
			classForm = { code: '', name: '', capacity: 30, building: '', floor: 0 };
		}
	}

	async function genericCreate(formType: string) {
		const token = localStorage.token ?? null;
		loadErr = null;
		try {
			if (formType === 'dept') {
				if (editingDeptId) {
					await updateDouDepartment(token, editingDeptId, deptForm);
					editingDeptId = '';
				} else {
					await createDouDepartment(token, deptForm);
				}
				deptForm = { code: '', name: '' };
			}
			if (formType === 'term') {
				if (editingTermId) {
					await updateDouTerm(token, editingTermId, {
						name: termForm.name,
						starts_at: termForm.starts_at,
						ends_at: termForm.ends_at,
						is_active: termForm.is_active
					});
					editingTermId = '';
				} else {
					await createDouTerm(token, { ...termForm, is_active: termForm.is_active });
				}
				termForm = {
					name: '',
					academic_year: '2025-2026',
					season: 'spring',
					starts_at: '',
					ends_at: '',
					is_active: false
				};
			}
			if (formType === 'course') {
				const did =
					courseForm.department_id ||
					(departments[0]?.id ?? '');
				if (!did && !editingCourseId) {
					loadErr = 'Ders için bölüm seçin veya en az bir bölüm oluşturun.';
					return;
				}
				if (editingCourseId) {
					await updateDouCourse(token, editingCourseId, {
						code: courseForm.code,
						name: courseForm.name,
						credits: courseForm.credits,
						akts: courseForm.akts,
						...(courseForm.department_id ? { department_id: courseForm.department_id } : {})
					});
					editingCourseId = '';
				} else {
					await createDouCourse(token, { ...courseForm, department_id: did });
				}
				courseForm = { code: '', name: '', credits: 3, akts: 5, department_id: '' };
			}
			if (formType === 'class') {
				if (editingClassId) {
					await updateDouClassroom(token, editingClassId, {
						code: classForm.code,
						name: classForm.name,
						capacity: classForm.capacity,
						building: classForm.building,
						floor: classForm.floor
					});
					editingClassId = '';
				} else {
					await createDouClassroom(token, classForm);
				}
				classForm = { code: '', name: '', capacity: 30, building: '', floor: 0 };
			}
			formSaved[formType] = true;
			await loadPage();
		} catch (e: unknown) {
			formSaved[formType] = false;
			loadErr = e instanceof Error ? e.message : 'Kayıt eklenemedi.';
		}
	}

	async function removeCatalogItem(
		formType: 'dept' | 'term' | 'course' | 'class',
		id: string
	) {
		if (!browser || !confirm('Silmek istediğinize emin misiniz?')) return;
		const token = localStorage.token ?? null;
		loadErr = null;
		try {
			if (formType === 'dept') await deleteDouDepartment(token, id);
			if (formType === 'term') await deleteDouTerm(token, id);
			if (formType === 'course') await deleteDouCourse(token, id);
			if (formType === 'class') await deleteDouClassroom(token, id);
			cancelCatalogEdits(formType);
			await loadPage();
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Silinemedi.';
		}
	}

	function selectRole(id: string) {
		selectedRoleId = id;
		const r = roles.find((x) => x.id === id);
		rolePermissions = r ? [...r.permissions] : [];
		rolesSaved = false;
	}

	function togglePerm(perm: string) {
		if (rolePermissions.includes(perm)) rolePermissions = rolePermissions.filter((p) => p !== perm);
		else rolePermissions = [...rolePermissions, perm];
	}
</script>

<svelte:head><title>OBS Admin — {pageTitle}</title></svelte:head>

<ObsShell {activePath} role="admin">
	<span slot="userline">{$user?.name ?? 'Admin'} • {pageTitle}</span>

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
			<!-- KULLANICI YÖNETİMİ                                           -->
			<!-- ============================================================ -->
		{:else if apiKey === 'users'}
			<div class="flex flex-wrap items-center gap-3">
				<input
					bind:value={userSearch}
					on:input={() => loadPage()}
					placeholder="Ad veya e-posta ara…"
					class="w-56 rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
				/>
				<select
					bind:value={userRoleFilter}
					on:change={() => loadPage()}
					class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5"
				>
					<option value="">Tüm roller</option>
					{#each ADMIN_USER_ROLE_OPTIONS as ro}
						<option value={ro.value}>{ro.label} ({ro.value})</option>
					{/each}
				</select>
				<button
					on:click={() => {
						newUser = emptyNewUser();
						createUserErr = null;
						showUserModal = true;
					}}
					type="button"
					class="ml-auto rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
				>
					+ Kullanıcı Ekle
				</button>
			</div>

			<p class="mb-3 text-xs text-slate-500 dark:text-slate-400">
				<strong>Open WebUI</strong> (Ayarlar → Kullanıcı ekle / <code class="rounded bg-slate-100 px-1 dark:bg-white/10">/api/v1/auths/add</code>)
				yalnızca <code class="rounded bg-slate-100 px-1 dark:bg-white/10">user</code> tablosuna yazar; OBS özlük için bu sayfadan
				<strong>+ Kullanıcı Ekle</strong> kullanın veya listede ilgili öğrenci için <strong>Özlük</strong> ile kayıt oluşturun.
			</p>

			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Ad Soyad</th>
								<th class="px-4 py-3 text-left">E-posta</th>
								<th class="px-4 py-3 text-center">Rol</th>
								<th class="px-4 py-3 text-center">Durum</th>
								<th class="px-4 py-3 text-center">Kayıt</th>
								<th class="px-4 py-3 text-center">İşlem</th>
							</tr>
						</thead>
						<tbody>
							{#each users as u}
								<tr
									class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 transition-colors"
								>
									<td class="px-4 py-3 font-medium">{u.full_name}</td>
									<td class="px-4 py-3 text-xs text-slate-500">{u.email}</td>
									<td class="px-4 py-3 text-center">
										<select
											value={u.role}
											on:change={(e) => changeUserRole(u, (e.target as HTMLSelectElement).value)}
											class="max-w-[11rem] rounded-lg border border-black/10 bg-white px-2 py-1 text-xs outline-none dark:border-white/10 dark:bg-white/5"
										>
											{#each ADMIN_USER_ROLE_OPTIONS as ro}
												<option value={ro.value}>{ro.label}</option>
											{/each}
											{#if !ADMIN_USER_ROLE_OPTIONS.some((ro) => ro.value === u.role)}
												<option value={u.role}>{adminUserRoleLabel(u.role)} ({u.role})</option>
											{/if}
										</select>
									</td>
									<td class="px-4 py-3 text-center">
										<span
											class="rounded-full px-2 py-0.5 text-xs font-medium {u.is_active
												? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
												: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}"
										>
											{u.is_active ? 'Aktif' : 'Pasif'}
										</span>
									</td>
									<td class="px-4 py-3 text-center text-xs text-slate-400">{u.created_at}</td>
									<td class="px-4 py-3 text-center">
										<div class="flex flex-wrap items-center justify-center gap-1">
											{#if u.role === 'user' || u.role === 'pending'}
												<button
													on:click={() => openOzlukModal(u)}
													type="button"
													class="rounded-lg border border-sky-200 bg-sky-50 px-2 py-1 text-xs font-medium text-sky-800 hover:bg-sky-100 dark:border-sky-800/50 dark:bg-sky-950/40 dark:text-sky-200 dark:hover:bg-sky-900/40 transition-colors"
													title="obs_student_profiles kaydı oluştur veya tamamla"
												>
													Özlük
												</button>
											{/if}
											<button
												on:click={() => toggleUserActive(u)}
												type="button"
												class="rounded-lg border border-black/10 px-2 py-1 text-xs hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5 transition-colors"
											>
												{u.is_active ? 'Dondur' : 'Aktifleştir'}
											</button>
										</div>
									</td>
								</tr>
							{:else}
								<tr
									><td colspan="6" class="px-4 py-8 text-center text-sm text-slate-400"
										>Kullanıcı bulunamadı.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			<!-- Yeni kullanıcı modal (OBS özlük: öğrenci / akademisyen) -->
			{#if showUserModal}
				<div
					class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-3"
				>
					<div
						class="flex max-h-[92vh] w-full max-w-2xl flex-col rounded-2xl border border-black/10 bg-white shadow-2xl dark:border-white/10 dark:bg-slate-900"
					>
						<div
							class="flex shrink-0 items-center justify-between border-b border-black/5 px-5 py-4 dark:border-white/10"
						>
							<div>
								<div class="font-bold">Yeni kullanıcı</div>
								<p class="mt-0.5 text-[11px] text-slate-400">
									Öğrenci → <code class="rounded bg-slate-100 px-1 dark:bg-white/10">obs_student_profiles</code>
									· Akademisyen →
									<code class="rounded bg-slate-100 px-1 dark:bg-white/10">obs_academic_profiles</code>
								</p>
							</div>
							<button
								on:click={() => (showUserModal = false)}
								type="button"
								class="text-slate-400 hover:text-slate-700">✕</button
							>
						</div>
						<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
							{#if createUserErr}
								<div
									class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200"
								>
									{createUserErr}
								</div>
							{/if}
							<div class="space-y-4">
								<div class="text-xs font-bold uppercase tracking-wide text-slate-400">
									Hesap (user tablosu)
								</div>
								<div class="grid gap-3 sm:grid-cols-2">
									<label class="block sm:col-span-2">
										<div class="mb-1 text-xs font-semibold text-slate-500">Ad Soyad *</div>
										<input
											bind:value={newUser.full_name}
											type="text"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">E-posta *</div>
										<input
											bind:value={newUser.email}
											type="email"
											autocomplete="off"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Parola *</div>
										<input
											bind:value={newUser.password}
											type="password"
											autocomplete="new-password"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Rol *</div>
										<select
											bind:value={newUser.role}
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										>
											{#each ADMIN_USER_ROLE_OPTIONS as ro}
												<option value={ro.value}>{ro.label} ({ro.value})</option>
											{/each}
										</select>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Kullanıcı adı</div>
										<input
											bind:value={newUser.username}
											type="text"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Cinsiyet</div>
										<input
											bind:value={newUser.gender}
											type="text"
											placeholder="örn. Erkek / Kadın"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Doğum tarihi</div>
										<input
											bind:value={newUser.date_of_birth}
											type="date"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
									<label class="block sm:col-span-2">
										<div class="mb-1 text-xs font-semibold text-slate-500">
											Telefon (user.info içinde saklanır)
										</div>
										<input
											bind:value={newUser.phone}
											type="tel"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
								</div>

								{#if newUser.role === 'user' || newUser.role === 'pending'}
									<div
										class="border-t border-black/5 pt-4 dark:border-white/10"
									>
										<div class="mb-2 text-xs font-bold uppercase tracking-wide text-sky-600 dark:text-sky-400">
											Öğrenci özlük — zorunlu
										</div>
										<div class="grid gap-3 sm:grid-cols-2">
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Öğrenci numarası *</div>
												<input
													bind:value={newUser.student_profile.student_number}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Bölüm *</div>
												<select
													bind:value={newUser.student_profile.department_id}
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												>
													<option value="">— Seçin —</option>
													{#each departments as d}
														<option value={d.id}>{d.code} — {d.name}</option>
													{/each}
												</select>
											</label>
										</div>
										<div class="mt-3 text-xs font-bold uppercase tracking-wide text-slate-400">
											İsteğe bağlı (obs_student_profiles)
										</div>
										<div class="mt-2 grid gap-3 sm:grid-cols-2">
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Kayıt tarihi</div>
												<input
													bind:value={newUser.student_profile.enrollment_date}
													type="date"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Sınıf / yıl</div>
												<input
													bind:value={newUser.student_profile.class_year}
													type="number"
													min="1"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Program</div>
												<input
													bind:value={newUser.student_profile.program}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">GNO</div>
												<input
													bind:value={newUser.student_profile.gpa}
													type="number"
													step="0.01"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Tamamlanan AKTS</div>
												<input
													bind:value={newUser.student_profile.completed_akts}
													type="number"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Gerekli AKTS</div>
												<input
													bind:value={newUser.student_profile.total_akts_required}
													type="number"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Durum</div>
												<input
													bind:value={newUser.student_profile.status}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="flex items-center gap-2 pt-6 text-sm">
												<input
													type="checkbox"
													bind:checked={newUser.student_profile.is_financially_eligible}
													class="rounded border-black/20"
												/>
												Mali uygun
											</label>
											<label class="block sm:col-span-2">
												<div class="mb-1 text-xs font-semibold text-slate-500">
													Öğrenci telefonu (özlük tablosu)
												</div>
												<input
													bind:value={newUser.student_profile.phone}
													type="tel"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block sm:col-span-2">
												<div class="mb-1 text-xs font-semibold text-slate-500">Adres</div>
												<input
													bind:value={newUser.student_profile.address}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Acil kişi</div>
												<input
													bind:value={newUser.student_profile.emergency_contact}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Acil tel</div>
												<input
													bind:value={newUser.student_profile.emergency_phone}
													type="tel"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">T.C. kimlik</div>
												<input
													bind:value={newUser.student_profile.tc_kimlik_no}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Doğum (özlük)</div>
												<input
													bind:value={newUser.student_profile.birth_date}
													type="date"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Doğum yeri</div>
												<input
													bind:value={newUser.student_profile.birth_place}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Uyruk</div>
												<input
													bind:value={newUser.student_profile.nationality}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Anne adı</div>
												<input
													bind:value={newUser.student_profile.mother_name}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Baba adı</div>
												<input
													bind:value={newUser.student_profile.father_name}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block sm:col-span-2">
												<div class="mb-1 text-xs font-semibold text-slate-500">Lise adı</div>
												<input
													bind:value={newUser.student_profile.high_school_name}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Lise mezuniyet yılı</div>
												<input
													bind:value={newUser.student_profile.high_school_graduation_year}
													type="number"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Program yarıyılı</div>
												<input
													bind:value={newUser.student_profile.program_semester_number}
													type="number"
													min="1"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
										</div>
									</div>
								{/if}

								{#if newUser.role === 'academician'}
									<div class="border-t border-black/5 pt-4 dark:border-white/10">
										<div class="mb-2 text-xs font-bold uppercase tracking-wide text-violet-600 dark:text-violet-400">
											Akademik profil — zorunlu
										</div>
										<div class="grid gap-3 sm:grid-cols-2">
											<label class="block sm:col-span-2">
												<div class="mb-1 text-xs font-semibold text-slate-500">Bölüm *</div>
												<select
													bind:value={newUser.academic_profile.department_id}
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												>
													<option value="">— Seçin —</option>
													{#each departments as d}
														<option value={d.id}>{d.code} — {d.name}</option>
													{/each}
												</select>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Sicil no</div>
												<input
													bind:value={newUser.academic_profile.staff_number}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Unvan</div>
												<input
													bind:value={newUser.academic_profile.title}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">Ofis</div>
												<input
													bind:value={newUser.academic_profile.office}
													type="text"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
											<label class="block">
												<div class="mb-1 text-xs font-semibold text-slate-500">
													Telefon (akademik özlük)
												</div>
												<input
													bind:value={newUser.academic_profile.phone}
													type="tel"
													class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
												/>
											</label>
										</div>
									</div>
								{/if}

								{#if newUser.role === 'admin'}
									<p class="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-white/5">
										<strong>Admin</strong> için yalnızca Open WebUI kullanıcı kaydı oluşturulur; OBS özlük
										tablosu eklenmez.
									</p>
								{/if}
							</div>
						</div>
						<div
							class="flex shrink-0 gap-2 border-t border-black/5 px-5 py-4 dark:border-white/10"
						>
							<button
								on:click={createUser}
								disabled={userCreating}
								type="button"
								class="flex-1 rounded-lg bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50"
							>
								{userCreating ? 'Oluşturuluyor…' : 'Oluştur'}
							</button>
							<button
								on:click={() => (showUserModal = false)}
								type="button"
								class="rounded-lg border border-black/10 px-5 py-2.5 text-sm hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
							>
								İptal
							</button>
						</div>
					</div>
				</div>
			{/if}

			{#if showOzlukModal && ozlukTarget}
				<div
					class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm p-3"
				>
					<div
						class="flex max-h-[92vh] w-full max-w-2xl flex-col rounded-2xl border border-black/10 bg-white shadow-2xl dark:border-white/10 dark:bg-slate-900"
					>
						<div
							class="flex shrink-0 items-center justify-between border-b border-black/5 px-5 py-4 dark:border-white/10"
						>
							<div>
								<div class="font-bold">Öğrenci özlüğü</div>
								<p class="mt-0.5 text-[11px] text-slate-400">
									{ozlukTarget.full_name} · {ozlukTarget.email}
								</p>
							</div>
							<button
								on:click={() => (showOzlukModal = false)}
								type="button"
								class="text-slate-400 hover:text-slate-700">✕</button
							>
						</div>
						<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
							{#if ozlukErr}
								<div
									class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-200"
								>
									{ozlukErr}
								</div>
							{/if}
							<p class="mb-4 text-xs text-slate-500 dark:text-slate-400">
								Kayıt <code class="rounded bg-slate-100 px-1 dark:bg-white/10">obs_student_profiles</code>
								tablosuna yazılır; zaten varsa mevcut kayıt korunur.
							</p>
							<div class="border-t border-black/5 pt-4 dark:border-white/10">
								<div class="mb-2 text-xs font-bold uppercase tracking-wide text-sky-600 dark:text-sky-400">
									Zorunlu alanlar
								</div>
								<div class="grid gap-3 sm:grid-cols-2">
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Öğrenci numarası *</div>
										<input
											bind:value={ozlukSp.student_number}
											type="text"
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										/>
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Bölüm *</div>
										<select
											bind:value={ozlukSp.department_id}
											class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
										>
											<option value="">— Seçin —</option>
											{#each departments as d}
												<option value={d.id}>{d.code} — {d.name}</option>
											{/each}
										</select>
									</label>
								</div>
								<div class="mt-3 text-xs font-bold uppercase tracking-wide text-slate-400">
									İsteğe bağlı
								</div>
								<div class="mt-2 grid gap-3 sm:grid-cols-2">
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Kayıt tarihi</div>
										<input bind:value={ozlukSp.enrollment_date} type="date" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Sınıf / yıl</div>
										<input bind:value={ozlukSp.class_year} type="number" min="1" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Program</div>
										<input bind:value={ozlukSp.program} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">GNO</div>
										<input bind:value={ozlukSp.gpa} type="number" step="0.01" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Tamamlanan AKTS</div>
										<input bind:value={ozlukSp.completed_akts} type="number" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Gerekli AKTS</div>
										<input bind:value={ozlukSp.total_akts_required} type="number" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Durum</div>
										<input bind:value={ozlukSp.status} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="flex items-center gap-2 pt-6 text-sm">
										<input type="checkbox" bind:checked={ozlukSp.is_financially_eligible} class="rounded border-black/20" />
										Mali uygun
									</label>
									<label class="block sm:col-span-2">
										<div class="mb-1 text-xs font-semibold text-slate-500">Öğrenci telefonu</div>
										<input bind:value={ozlukSp.phone} type="tel" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block sm:col-span-2">
										<div class="mb-1 text-xs font-semibold text-slate-500">Adres</div>
										<input bind:value={ozlukSp.address} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Acil kişi</div>
										<input bind:value={ozlukSp.emergency_contact} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Acil tel</div>
										<input bind:value={ozlukSp.emergency_phone} type="tel" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">T.C. kimlik</div>
										<input bind:value={ozlukSp.tc_kimlik_no} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Doğum</div>
										<input bind:value={ozlukSp.birth_date} type="date" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Doğum yeri</div>
										<input bind:value={ozlukSp.birth_place} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Uyruk</div>
										<input bind:value={ozlukSp.nationality} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Anne adı</div>
										<input bind:value={ozlukSp.mother_name} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Baba adı</div>
										<input bind:value={ozlukSp.father_name} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block sm:col-span-2">
										<div class="mb-1 text-xs font-semibold text-slate-500">Lise adı</div>
										<input bind:value={ozlukSp.high_school_name} type="text" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Lise mezuniyet yılı</div>
										<input bind:value={ozlukSp.high_school_graduation_year} type="number" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
									<label class="block">
										<div class="mb-1 text-xs font-semibold text-slate-500">Program yarıyılı</div>
										<input bind:value={ozlukSp.program_semester_number} type="number" min="1" class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800" />
									</label>
								</div>
							</div>
						</div>
						<div class="flex shrink-0 gap-2 border-t border-black/5 px-5 py-4 dark:border-white/10">
							<button
								on:click={submitOzluk}
								disabled={ozlukSaving}
								type="button"
								class="flex-1 rounded-lg bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50"
							>
								{ozlukSaving ? 'Kaydediliyor…' : 'Özlük kaydet'}
							</button>
							<button
								on:click={() => (showOzlukModal = false)}
								type="button"
								class="rounded-lg border border-black/10 px-5 py-2.5 text-sm hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
							>
								İptal
							</button>
						</div>
					</div>
				</div>
			{/if}

			<!-- ============================================================ -->
			<!-- ROL YÖNETİMİ                                                 -->
			<!-- ============================================================ -->
		{:else if apiKey === 'roles'}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<!-- Sol: Rol listesi -->
				<div
					class="rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div
						class="border-b border-black/5 px-5 py-3 text-xs font-bold text-slate-400 dark:border-white/10"
					>
						ROLLER
					</div>
					{#each roles as r}
						<button
							on:click={() => selectRole(r.id)}
							type="button"
							class="flex w-full items-center justify-between border-t border-black/5 px-5 py-3 text-left text-sm transition-colors dark:border-white/10
								{selectedRoleId === r.id
								? 'bg-sky-50 dark:bg-sky-900/10'
								: 'hover:bg-slate-50 dark:hover:bg-white/5'}"
						>
							<div>
								<div class="font-semibold">{r.name}</div>
								<div class="text-xs text-slate-400">{r.description}</div>
							</div>
							<span
								class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-white/10 dark:text-slate-300"
								>{r.permissions.length}</span
							>
						</button>
					{/each}
				</div>

				<!-- Sağ: Permission checkbox -->
				<div
					class="col-span-2 rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-3 flex items-center justify-between">
						<div class="font-semibold">
							{roles.find((r) => r.id === selectedRoleId)?.name ?? 'Rol Seç'} — İzinler
						</div>
						{#if rolesSaved}<span class="text-xs text-emerald-600 dark:text-emerald-400"
								>Kaydedildi ✓</span
							>{/if}
					</div>
					<div class="grid grid-cols-2 gap-2">
						{#each ALL_PERMISSIONS as perm}
							<label
								class="flex cursor-pointer items-center gap-2 rounded-lg border border-black/5 px-3 py-2 text-xs hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
							>
								<input
									type="checkbox"
									checked={rolePermissions.includes(perm)}
									on:change={() => togglePerm(perm)}
									class="accent-sky-500"
								/>
								<span class="font-mono text-slate-600 dark:text-slate-300">{perm}</span>
							</label>
						{/each}
					</div>
					<button
						on:click={saveRolePermissions}
						disabled={rolesSaving}
						type="button"
						class="mt-4 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
					>
						{rolesSaving ? 'Kaydediliyor…' : 'Kaydet'}
					</button>
				</div>
			</div>

			<!-- ============================================================ -->
			<!-- BÖLÜM / DÖNEM / DERS / DERSLİK (Generic CRUD)              -->
			<!-- ============================================================ -->
		{:else if apiKey === 'departments'}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<div
					class="col-span-2 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div
						class="grid grid-cols-12 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
					>
						<div class="col-span-2">Kod</div>
						<div class="col-span-6">Ad</div>
						<div class="col-span-4 text-right">İşlem</div>
					</div>
					{#each departments as d}
						<div
							class="grid grid-cols-12 items-center border-t border-black/5 px-5 py-3 text-sm dark:border-white/10"
						>
							<div class="col-span-2 font-mono font-semibold text-slate-500">{d.code}</div>
							<div class="col-span-6">{d.name}</div>
							<div class="col-span-4 flex justify-end gap-1">
								<button
									type="button"
									on:click={() => {
										editingDeptId = d.id;
										deptForm = { code: d.code, name: d.name };
									}}
									class="rounded-lg border border-sky-200 px-2 py-1 text-xs font-semibold text-sky-600 hover:bg-sky-50 dark:border-sky-900/40 dark:text-sky-400"
								>
									Düzenle
								</button>
								<button
									type="button"
									on:click={() => removeCatalogItem('dept', d.id)}
									class="rounded-lg border border-red-200 px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 dark:border-red-900/40 dark:text-red-400"
								>
									Sil
								</button>
							</div>
						</div>
					{:else}<div class="px-5 py-8 text-center text-sm text-slate-400">Kayıt yok.</div>{/each}
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-sm">
						{editingDeptId ? 'Bölüm Düzenle' : 'Yeni Bölüm'}
					</div>
					{#if formSaved['dept']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Kaydedildi.
						</div>{/if}
					<div class="space-y-3">
						<label class="block"
							><div class="mb-1 text-xs font-semibold text-slate-500">Kod</div>
							<input
								bind:value={deptForm.code}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
							/></label
						>
						<label class="block"
							><div class="mb-1 text-xs font-semibold text-slate-500">Ad</div>
							<input
								bind:value={deptForm.name}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
							/></label
						>
						<div class="flex flex-col gap-2">
							{#if editingDeptId}
								<button
									type="button"
									on:click={() => cancelCatalogEdits('dept')}
									class="w-full rounded-lg border border-black/10 py-2 text-sm font-semibold text-slate-600 dark:border-white/10"
								>
									İptal
								</button>
							{/if}
							<button
								on:click={() => genericCreate('dept')}
								type="button"
								class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
								>{editingDeptId ? 'Güncelle' : 'Ekle'}</button
							>
						</div>
					</div>
				</div>
			</div>
		{:else if apiKey === 'terms'}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<div
					class="col-span-2 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div
						class="grid grid-cols-12 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
					>
						<div class="col-span-4">Dönem</div>
						<div class="col-span-2">Başlangıç</div>
						<div class="col-span-2">Bitiş</div>
						<div class="col-span-4 text-right">İşlem</div>
					</div>
					{#each terms as t}
						<div
							class="grid grid-cols-12 items-center border-t border-black/5 px-5 py-3 text-sm dark:border-white/10"
						>
							<div class="col-span-4 font-medium">
								{t.name}
								{#if t.is_active}<span
										class="ml-2 rounded-full bg-sky-100 px-1.5 py-0.5 text-[10px] font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
										>Aktif</span
									>{/if}
							</div>
							<div class="col-span-2 text-xs text-slate-400">{t.starts_at}</div>
							<div class="col-span-2 text-xs text-slate-400">{t.ends_at}</div>
							<div class="col-span-4 flex justify-end gap-1">
								<button
									type="button"
									on:click={() => {
										editingTermId = t.id;
										termForm = {
											name: t.name,
											academic_year: t.academic_year ?? '2025-2026',
											season: t.season ?? 'spring',
											starts_at: t.starts_at ?? '',
											ends_at: t.ends_at ?? '',
											is_active: !!t.is_active
										};
									}}
									class="rounded-lg border border-sky-200 px-2 py-1 text-xs font-semibold text-sky-600 hover:bg-sky-50 dark:border-sky-900/40 dark:text-sky-400"
								>
									Düzenle
								</button>
								<button
									type="button"
									on:click={() => removeCatalogItem('term', t.id)}
									class="rounded-lg border border-red-200 px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 dark:border-red-900/40 dark:text-red-400"
								>
									Sil
								</button>
							</div>
						</div>
					{:else}<div class="px-5 py-8 text-center text-sm text-slate-400">Dönem yok.</div>{/each}
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-sm">
						{editingTermId ? 'Dönem Düzenle' : 'Yeni Dönem'}
					</div>
					{#if formSaved['term']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Kaydedildi.
						</div>{/if}
					<div class="space-y-3">
						{#each [['Ad', 'name', 'text'], ['Akademik Yıl', 'academic_year', 'text'], ['Başlangıç', 'starts_at', 'date'], ['Bitiş', 'ends_at', 'date']] as [lbl, field, type]}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">{lbl}</div>
								<input
									bind:value={termForm[field as keyof typeof termForm]}
									{type}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
								/>
							</label>
						{/each}
						<label class="flex cursor-pointer items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
							<input type="checkbox" bind:checked={termForm.is_active} class="rounded border-black/20" />
							Aktif dönem
						</label>
						<div class="flex flex-col gap-2">
							{#if editingTermId}
								<button
									type="button"
									on:click={() => cancelCatalogEdits('term')}
									class="w-full rounded-lg border border-black/10 py-2 text-sm font-semibold text-slate-600 dark:border-white/10"
								>
									İptal
								</button>
							{/if}
							<button
								on:click={() => genericCreate('term')}
								type="button"
								class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
								>{editingTermId ? 'Güncelle' : 'Ekle'}</button
							>
						</div>
					</div>
				</div>
			</div>
		{:else if apiKey === 'courses'}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<div
					class="col-span-2 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead
								class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
							>
								<tr
									><th class="px-4 py-3 text-left">Kod</th><th class="px-4 py-3 text-left">Ad</th
									><th class="px-4 py-3 text-center">K</th><th class="px-4 py-3 text-center"
										>AKTS</th
									><th class="px-4 py-3 text-right">İşlem</th></tr
								>
							</thead>
							<tbody>
								{#each courses as c}
									<tr class="border-t border-black/5 dark:border-white/10">
										<td class="px-4 py-3 font-mono text-xs font-semibold text-slate-500"
											>{c.code}</td
										>
										<td class="px-4 py-3 font-medium">{c.name}</td>
										<td class="px-4 py-3 text-center">{c.credits}</td>
										<td class="px-4 py-3 text-center">{c.akts}</td>
										<td class="px-4 py-3 text-right">
											<button
												type="button"
												on:click={() => {
													editingCourseId = c.id;
													courseForm = {
														code: c.code,
														name: c.name,
														credits: c.credits,
														akts: c.akts,
														department_id: c.department_id ?? ''
													};
												}}
												class="mr-1 rounded-lg border border-sky-200 px-2 py-1 text-xs font-semibold text-sky-600 dark:border-sky-900/40 dark:text-sky-400"
											>
												Düzenle
											</button>
											<button
												type="button"
												on:click={() => removeCatalogItem('course', c.id)}
												class="rounded-lg border border-red-200 px-2 py-1 text-xs font-semibold text-red-600 dark:border-red-900/40 dark:text-red-400"
											>
												Sil
											</button>
										</td>
									</tr>
								{:else}<tr
										><td colspan="5" class="px-4 py-8 text-center text-sm text-slate-400"
											>Ders yok.</td
										></tr
									>{/each}
							</tbody>
						</table>
					</div>
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-sm">
						{editingCourseId ? 'Ders Düzenle' : 'Yeni Ders'}
					</div>
					{#if formSaved['course']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Kaydedildi.
						</div>{/if}
					<div class="space-y-3">
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">Bölüm</div>
							<select
								bind:value={courseForm.department_id}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
							>
								<option value="">— Bölüm —</option>
								{#each departments as d}
									<option value={d.id}>{d.code} — {d.name}</option>
								{/each}
							</select>
						</label>
						{#each [['Kod', 'code', 'text'], ['Ad', 'name', 'text']] as [lbl, field, type]}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">{lbl}</div>
								<input
									bind:value={courseForm[field as keyof typeof courseForm]}
									{type}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
								/>
							</label>
						{/each}
						<div class="grid grid-cols-2 gap-2">
							<label class="block"
								><div class="mb-1 text-xs font-semibold text-slate-500">Kredi</div>
								<input
									type="number"
									bind:value={courseForm.credits}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
								/></label
							>
							<label class="block"
								><div class="mb-1 text-xs font-semibold text-slate-500">AKTS</div>
								<input
									type="number"
									bind:value={courseForm.akts}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
								/></label
							>
						</div>
						<div class="flex flex-col gap-2">
							{#if editingCourseId}
								<button
									type="button"
									on:click={() => cancelCatalogEdits('course')}
									class="w-full rounded-lg border border-black/10 py-2 text-sm font-semibold text-slate-600 dark:border-white/10"
								>
									İptal
								</button>
							{/if}
							<button
								on:click={() => genericCreate('course')}
								type="button"
								class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
								>{editingCourseId ? 'Güncelle' : 'Ekle'}</button
							>
						</div>
					</div>
				</div>
			</div>
		{:else if apiKey === 'classrooms'}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<div
					class="col-span-2 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div
						class="grid grid-cols-12 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
					>
						<div class="col-span-2">Kod</div>
						<div class="col-span-5">Ad</div>
						<div class="col-span-2">Kapasite</div>
						<div class="col-span-3 text-right">İşlem</div>
					</div>
					{#each classrooms as c}
						<div
							class="grid grid-cols-12 items-center border-t border-black/5 px-5 py-3 text-sm dark:border-white/10"
						>
							<div class="col-span-2 font-mono font-semibold text-slate-500">{c.code}</div>
							<div class="col-span-5">{c.name}</div>
							<div class="col-span-2 text-slate-500">{c.capacity}</div>
							<div class="col-span-3 flex justify-end gap-1">
								<button
									type="button"
									on:click={() => {
										editingClassId = c.id;
										classForm = {
											code: c.code,
											name: c.name,
											capacity: c.capacity,
											building: c.building ?? '',
											floor: c.floor ?? 0
										};
									}}
									class="rounded-lg border border-sky-200 px-2 py-1 text-xs font-semibold text-sky-600 dark:border-sky-900/40 dark:text-sky-400"
								>
									Düzenle
								</button>
								<button
									type="button"
									on:click={() => removeCatalogItem('class', c.id)}
									class="rounded-lg border border-red-200 px-2 py-1 text-xs font-semibold text-red-600 dark:border-red-900/40 dark:text-red-400"
								>
									Sil
								</button>
							</div>
						</div>
					{:else}<div class="px-5 py-8 text-center text-sm text-slate-400">Derslik yok.</div>{/each}
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-sm">
						{editingClassId ? 'Derslik Düzenle' : 'Yeni Derslik'}
					</div>
					{#if formSaved['class']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Kaydedildi.
						</div>{/if}
					<div class="space-y-3">
						{#each [['Kod', 'code', 'text'], ['Ad', 'name', 'text'], ['Bina', 'building', 'text']] as [lbl, field, type]}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">{lbl}</div>
								<input
									bind:value={classForm[field as keyof typeof classForm]}
									{type}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
								/>
							</label>
						{/each}
						<label class="block"
							><div class="mb-1 text-xs font-semibold text-slate-500">Kapasite</div>
							<input
								type="number"
								bind:value={classForm.capacity}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
							/></label
						>
						<div class="flex flex-col gap-2">
							{#if editingClassId}
								<button
									type="button"
									on:click={() => cancelCatalogEdits('class')}
									class="w-full rounded-lg border border-black/10 py-2 text-sm font-semibold text-slate-600 dark:border-white/10"
								>
									İptal
								</button>
							{/if}
							<button
								on:click={() => genericCreate('class')}
								type="button"
								class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
								>{editingClassId ? 'Güncelle' : 'Ekle'}</button
							>
						</div>
					</div>
				</div>
			</div>
		{:else if apiKey === 'student-advisors'}
			<div class="space-y-5">
				<!-- Filtre + Toplu atama -->
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-3 flex items-center justify-between">
						<div>
							<div class="text-sm font-bold text-slate-800 dark:text-slate-100">
								Öğrenci → Danışman (obs_student_advisors)
							</div>
							<p class="text-xs text-slate-500">
								Öğrenci listesinden ilgili kişileri seçip toplu danışman atayın veya
								satır içinden tek tek değiştirin. Mevcut danışman tabloda görünür.
							</p>
						</div>
						<button
							type="button"
							on:click={() => void reloadStudentAdvisorsList()}
							class="rounded-lg border border-black/10 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10"
							disabled={studentAdvisorsLoading}
						>
							{studentAdvisorsLoading ? 'Yükleniyor…' : '↺ Yenile'}
						</button>
					</div>

					{#if studentAdvisorsInfo}
						<div
							class="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-300"
						>
							{studentAdvisorsInfo}
						</div>
					{/if}
					{#if studentAdvisorsErr}
						<div
							class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-400"
						>
							{studentAdvisorsErr}
						</div>
					{/if}

					<div class="grid grid-cols-1 gap-3 md:grid-cols-12">
						<label class="md:col-span-3 block">
							<span class="mb-1 block text-xs font-semibold text-slate-500">Ara</span>
							<input
								type="text"
								placeholder="Ad, e-posta, öğrenci no…"
								bind:value={studentAdvisorsSearch}
								on:keydown={(e) => {
									if (e.key === 'Enter') void reloadStudentAdvisorsList();
								}}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
							/>
						</label>
						<label class="md:col-span-3 block">
							<span class="mb-1 block text-xs font-semibold text-slate-500">Bölüm</span>
							<select
								bind:value={studentAdvisorsDeptId}
								on:change={() => void reloadStudentAdvisorsList()}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
							>
								<option value="">Hepsi</option>
								{#each departments as d}
									<option value={d.id}>{d.code ? `${d.code} — ` : ''}{d.name}</option>
								{/each}
							</select>
						</label>
						<label class="md:col-span-3 block">
							<span class="mb-1 block text-xs font-semibold text-slate-500"
								>Mevcut Danışman</span
							>
							<select
								bind:value={studentAdvisorsAdvisorFilter}
								on:change={() => void reloadStudentAdvisorsList()}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
							>
								<option value="">Hepsi</option>
								{#each studentAdvisorsAdvisorOptions as ins}
									<option value={ins.user_id}>{studentAdvisorsAdvisorLabel(ins)}</option>
								{/each}
							</select>
						</label>
						<label
							class="md:col-span-3 flex items-center gap-2 self-end pb-1 text-xs font-medium text-slate-600 dark:text-slate-300"
						>
							<input
								type="checkbox"
								bind:checked={studentAdvisorsOnlyUnassigned}
								on:change={() => void reloadStudentAdvisorsList()}
								class="rounded border-black/20"
							/>
							Sadece danışmansız öğrenciler
						</label>
					</div>

					<div
						class="mt-4 flex flex-wrap items-end gap-3 rounded-lg border border-violet-100 bg-violet-50/40 p-3 dark:border-violet-900/30 dark:bg-violet-950/20"
					>
						<div class="text-xs font-semibold text-violet-700 dark:text-violet-300">
							Toplu Atama
						</div>
						<label class="flex-1 min-w-[260px] block">
							<span class="mb-1 block text-xs font-semibold text-slate-500"
								>Atanacak Danışman</span
							>
							<select
								bind:value={studentAdvisorsBulkAdvisor}
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
							>
								<option value="">— Danışmanlığı Kaldır —</option>
								{#each studentAdvisorsAdvisorOptions as ins}
									<option value={ins.user_id}>{studentAdvisorsAdvisorLabel(ins)}</option>
								{/each}
							</select>
						</label>
						<button
							type="button"
							on:click={() => void bulkAssignStudentAdvisor()}
							disabled={studentAdvisorsBulkSaving || studentAdvisorsSelectedIds.length === 0}
							class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-500 disabled:opacity-50"
						>
							{studentAdvisorsBulkSaving
								? 'Kaydediliyor…'
								: `Seçili ${studentAdvisorsSelectedIds.length} öğrenciye uygula`}
						</button>
					</div>
				</div>

				<!-- Liste -->
				<div
					class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div
						class="flex items-center justify-between border-b border-black/5 px-5 py-3 dark:border-white/10"
					>
						<div class="text-sm font-semibold text-slate-800 dark:text-slate-100">
							Öğrenciler
						</div>
						<div
							class="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
						>
							{studentAdvisorsRows.length} kayıt
						</div>
					</div>

					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead
								class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5"
							>
								<tr>
									<th class="px-3 py-2 text-left w-8">
										<input
											type="checkbox"
											checked={studentAdvisorsAllSelected}
											on:change={(e) =>
												toggleStudentAdvisorAll(
													(e.currentTarget as HTMLInputElement).checked
												)}
											class="rounded border-black/20"
										/>
									</th>
									<th class="px-3 py-2 text-left">Öğrenci No</th>
									<th class="px-3 py-2 text-left">Ad Soyad</th>
									<th class="px-3 py-2 text-left">Bölüm / Sınıf</th>
									<th class="px-3 py-2 text-left">Mevcut Danışman</th>
									<th class="px-3 py-2 text-left">Yeni Danışman</th>
									<th class="px-3 py-2 text-left">İşlem</th>
								</tr>
							</thead>
							<tbody>
								{#each studentAdvisorsRows as r (r.user_id)}
									<tr class="border-t border-black/5 dark:border-white/10">
										<td class="px-3 py-2">
											<input
												type="checkbox"
												bind:checked={studentAdvisorsSelected[r.user_id]}
												class="rounded border-black/20"
											/>
										</td>
										<td class="px-3 py-2 font-mono text-xs">{r.student_number || '—'}</td>
										<td class="px-3 py-2">
											<div class="font-medium">{r.full_name || r.email || r.user_id}</div>
											<div class="text-xs text-slate-400">{r.email}</div>
										</td>
										<td class="px-3 py-2 text-xs text-slate-500">
											{r.department_code
												? `${r.department_code} · `
												: ''}{r.department_name || '—'}
											<div class="text-[11px] text-slate-400">
												Sınıf {r.class_year || '—'} · {r.program || '—'}
											</div>
										</td>
										<td class="px-3 py-2 text-xs">
											{#if r.advisor_user_id}
												<div class="font-medium text-slate-700 dark:text-slate-200">
													{r.advisor_title ? `${r.advisor_title} ` : ''}{r.advisor_full_name ||
														r.advisor_email ||
														r.advisor_user_id}
												</div>
												<div class="text-[11px] text-slate-400">
													{r.advisor_email}
													{#if r.advisor_valid_from}
														· {r.advisor_valid_from} →
													{/if}
												</div>
											{:else}
												<span
													class="inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
													>Atanmadı</span
												>
											{/if}
										</td>
										<td class="px-3 py-2">
											<select
												bind:value={studentAdvisorsRowDraft[r.user_id]}
												class="w-full max-w-[16rem] rounded border border-black/10 px-2 py-1 text-xs dark:border-white/10 dark:bg-slate-900"
											>
												<option value="">— Atanmadı —</option>
												{#each studentAdvisorsAdvisorOptions as ins}
													<option value={ins.user_id}
														>{studentAdvisorsAdvisorLabel(ins)}</option
													>
												{/each}
											</select>
										</td>
										<td class="px-3 py-2">
											<button
												type="button"
												disabled={studentAdvisorsRowSavingId === r.user_id ||
													(studentAdvisorsRowDraft[r.user_id] ?? '') ===
														(r.advisor_user_id ?? '')}
												on:click={() =>
													void persistStudentAdvisor(
														r.user_id,
														studentAdvisorsRowDraft[r.user_id] ?? ''
													)}
												class="rounded-lg bg-violet-600 px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
											>
												{studentAdvisorsRowSavingId === r.user_id ? '…' : 'Kaydet'}
											</button>
											{#if r.advisor_user_id}
												<button
													type="button"
													disabled={studentAdvisorsRowSavingId === r.user_id}
													on:click={() => void persistStudentAdvisor(r.user_id, '')}
													class="ml-1 rounded-lg border border-red-200 px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/40 dark:text-red-400"
												>
													Kaldır
												</button>
											{/if}
										</td>
									</tr>
								{:else}
									<tr>
										<td colspan="7" class="px-3 py-10 text-center text-sm text-slate-400">
											{studentAdvisorsLoading ? 'Yükleniyor…' : 'Kriterlere uyan öğrenci yok.'}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			</div>
		{:else if apiKey === 'section-assignments'}
			<div class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5">
					<div class="mb-4 text-sm font-bold text-slate-800 dark:text-slate-100">
						Şube → Öğretim üyesi (obs_course_sections)
					</div>
					<p class="mb-4 text-xs text-slate-500">
						Döneme göre şubeleri listeleyip öğretim üyesi atayın.
					</p>
					<div class="mb-4 flex flex-wrap items-center gap-3">
						<label class="text-xs font-semibold text-slate-500">
							Dönem
							<select
								bind:value={assignmentTermId}
								on:change={() => void reloadAssignmentSectionsOnly()}
								class="ml-2 rounded-lg border border-black/10 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
							>
								{#each terms as tm}
									<option value={tm.id}>{tm.name}</option>
								{/each}
							</select>
						</label>
					</div>
					<div class="overflow-x-auto rounded-lg border border-black/10 dark:border-white/10">
						<table class="w-full text-sm">
							<thead class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5">
								<tr>
									<th class="px-3 py-2 text-left">Ders</th>
									<th class="px-3 py-2 text-center">Şb</th>
									<th class="px-3 py-2 text-left">Öğretim üyesi</th>
									<th class="px-3 py-2 text-left">Kaydet</th>
								</tr>
							</thead>
							<tbody>
								{#each assignmentSectionsList as sec}
									<tr class="border-t border-black/5 dark:border-white/10">
										<td class="px-3 py-2">
											<div class="font-medium">{String(sec.course_code ?? '')}</div>
											<div class="text-xs text-slate-400">{String(sec.course_name ?? '')}</div>
										</td>
										<td class="px-3 py-2 text-center text-xs">{sec.section_no ?? ''}</td>
										<td class="px-3 py-2">
											<select
												bind:value={sectionDraft[String(sec.id)]}
												class="max-w-[18rem] rounded border border-black/10 px-2 py-1 text-xs dark:border-white/10 dark:bg-slate-900"
											>
												<option value="">— Atanmadı —</option>
												{#each assignmentInstructorsAll as ins}
													<option value={ins.user_id}>
														{ins.full_name || ins.email || ins.user_id}
													</option>
												{/each}
											</select>
										</td>
										<td class="px-3 py-2">
											<button
												type="button"
												disabled={sectionInstrSavingId === String(sec.id)}
												on:click={() =>
													void persistSectionInstructor(
														String(sec.id),
														sectionDraft[String(sec.id)] ?? ''
													)}
												class="rounded-lg bg-violet-600 px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
											>
												{sectionInstrSavingId === String(sec.id) ? '…' : 'Kaydet'}
											</button>
										</td>
									</tr>
								{:else}
									<tr>
										<td colspan="4" class="px-3 py-8 text-center text-slate-400">
											Bu dönemde şube yok.
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
		{:else if apiKey === 'sections'}
			<div class="grid grid-cols-1 gap-6 lg:grid-cols-5">
				<!-- Sol — Form -->
				<div class="lg:col-span-2">
					<div
						class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
					>
						<div class="mb-4 flex items-center gap-2">
							<svg
								class="h-4 w-4 text-sky-500"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="2"
							>
								<path d="M12 4v16m8-8H4" />
							</svg>
							<span class="font-bold text-slate-800 dark:text-slate-100"
								>{editingSectionId ? 'Şube Düzenle' : 'Yeni Şube Aç'}</span
							>
						</div>

						{#if sectionSaved}
							<div
								class="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
							>
								✓ Kayıt başarılı.
							</div>
						{/if}
						{#if sectionErr}
							<div
								class="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400"
							>
								{sectionErr}
							</div>
						{/if}

						<div class="space-y-3">
							<!-- Ders -->
							<label class="block">
								<span class="mb-1 block text-xs font-semibold text-slate-500"
									>Ders <span class="text-red-400">*</span></span
								>
								<select
									bind:value={sectionForm.course_id}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
								>
									<option value="">— Ders seçin —</option>
									{#each courses as c}
										<option value={c.id}>{c.code} — {c.name}</option>
									{/each}
								</select>
							</label>

							<!-- Dönem -->
							<label class="block">
								<span class="mb-1 block text-xs font-semibold text-slate-500"
									>Dönem <span class="text-red-400">*</span></span
								>
								<select
									bind:value={sectionForm.term_id}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
								>
									<option value="">— Dönem seçin —</option>
									{#each terms as t}
										<option value={t.id}>{t.name}{t.is_active ? ' (Aktif)' : ''}</option>
									{/each}
								</select>
							</label>

							<!-- Akademisyen -->
							<label class="block">
								<span class="mb-1 block text-xs font-semibold text-slate-500"
									>Akademisyen <span class="text-red-400">*</span></span
								>
								<select
									bind:value={sectionForm.instructor_id}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
								>
									<option value="">— Hoca seçin —</option>
									{#each instructors as i}
										<option value={i.id}>{i.full_name}</option>
									{/each}
								</select>
							</label>

							<!-- Derslik + Şube No -->
							<div class="grid grid-cols-2 gap-3">
								<label class="block">
									<span class="mb-1 block text-xs font-semibold text-slate-500">Derslik</span>
									<select
										bind:value={sectionForm.classroom_id}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
									>
										<option value="">— Derslik —</option>
										{#each classrooms as cl}
											<option value={cl.id}>{cl.code} ({cl.capacity} kişi)</option>
										{/each}
									</select>
								</label>
								<label class="block">
									<span class="mb-1 block text-xs font-semibold text-slate-500">Şube No</span>
									<input
										type="number"
										min="1"
										max="10"
										bind:value={sectionForm.section_no}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
									/>
								</label>
							</div>

							<!-- Gün + Saat -->
							<div class="grid grid-cols-3 gap-3">
								<label class="block">
									<span class="mb-1 block text-xs font-semibold text-slate-500">Gün</span>
									<select
										bind:value={sectionForm.day_of_week}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
									>
										{#each DAYS as d}
											<option value={d}>{d}</option>
										{/each}
									</select>
								</label>
								<label class="block">
									<span class="mb-1 block text-xs font-semibold text-slate-500">Başlangıç</span>
									<select
										bind:value={sectionForm.start_time}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
									>
										{#each HOURS as h}
											<option value={h}>{h}</option>
										{/each}
									</select>
								</label>
								<label class="block">
									<span class="mb-1 block text-xs font-semibold text-slate-500">Bitiş</span>
									<select
										bind:value={sectionForm.end_time}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
									>
										{#each HOURS as h}
											<option value={h}>{h}</option>
										{/each}
									</select>
								</label>
							</div>

							<!-- Kontenjan -->
							<label class="block">
								<span class="mb-1 block text-xs font-semibold text-slate-500">Kontenjan</span>
								<input
									type="number"
									min="1"
									max="200"
									bind:value={sectionForm.capacity}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
								/>
							</label>

							<div class="flex flex-col gap-2">
								{#if editingSectionId}
									<button
										type="button"
										on:click={cancelSectionEdit}
										class="w-full rounded-lg border border-black/10 py-2 text-sm font-semibold text-slate-600 dark:border-white/10"
									>
										İptal
									</button>
								{/if}
								<button
									on:click={createSection}
									disabled={sectionSaving}
									type="button"
									class="w-full rounded-lg bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
								>
									{sectionSaving
										? 'Kaydediliyor…'
										: editingSectionId
											? 'Şubeyi Güncelle'
											: 'Şubeyi Oluştur'}
								</button>
							</div>
						</div>
					</div>
				</div>

				<!-- Sağ — Mevcut şubeler -->
				<div class="lg:col-span-3">
					<div
						class="rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
					>
						<div
							class="flex items-center justify-between border-b border-black/5 px-5 py-3 dark:border-white/10"
						>
							<span class="font-semibold text-slate-800 dark:text-slate-100">Mevcut Şubeler</span>
							<span
								class="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
							>
								{adminSections.length} şube
							</span>
						</div>
						{#if adminSections.length === 0}
							<div class="px-5 py-10 text-center text-sm text-slate-400">Henüz şube açılmamış.</div>
						{:else}
							<div class="overflow-x-auto">
								<table class="w-full text-sm">
									<thead>
										<tr
											class="border-b border-black/5 bg-slate-50/80 dark:border-white/10 dark:bg-white/5"
										>
											<th class="px-4 py-2 text-left text-xs font-bold text-slate-400">Kod</th>
											<th class="px-4 py-2 text-left text-xs font-bold text-slate-400">Ders</th>
											<th class="px-4 py-2 text-left text-xs font-bold text-slate-400"
												>Akademisyen</th
											>
											<th class="px-4 py-2 text-left text-xs font-bold text-slate-400">Gün/Saat</th>
											<th class="px-4 py-2 text-left text-xs font-bold text-slate-400">Derslik</th>
											<th class="px-4 py-2 text-center text-xs font-bold text-slate-400">Kont.</th>
											<th class="px-4 py-2 text-right text-xs font-bold text-slate-400">İşlem</th>
										</tr>
									</thead>
									<tbody>
										{#each adminSections as sec}
											{@const s = sec as Record<string, unknown>}
											<tr
												class="border-t border-black/5 hover:bg-slate-50/50 dark:border-white/10 dark:hover:bg-white/5"
											>
												<td class="px-4 py-2.5 font-mono text-xs font-semibold text-slate-500"
													>{s.course_code ?? '—'}</td
												>
												<td class="px-4 py-2.5">{s.course_name ?? s.course_id ?? '—'}</td>
												<td class="px-4 py-2.5 text-xs text-slate-600 dark:text-slate-300"
													>{s.instructor_label ?? '—'}</td
												>
												<td class="px-4 py-2.5 text-xs text-slate-500"
													>{s.day_of_week ?? '—'} {s.start_time ?? ''}</td
												>
												<td class="px-4 py-2.5 text-xs text-slate-500"
													>{s.classroom_code ?? s.classroom_id ?? '—'}</td
												>
												<td class="px-4 py-2.5 text-center text-xs">{s.capacity ?? '—'}</td>
												<td class="px-4 py-2.5 text-right text-xs">
													<button
														type="button"
														on:click={() => startSectionEdit(s)}
														class="mr-1 rounded border border-sky-200 px-2 py-0.5 font-semibold text-sky-600 dark:border-sky-900/40 dark:text-sky-400"
													>
														Düzenle
													</button>
													<button
														type="button"
														on:click={() => removeSectionRow(String(s.id ?? ''))}
														class="rounded border border-red-200 px-2 py-0.5 font-semibold text-red-600 dark:border-red-900/40 dark:text-red-400"
													>
														Sil
													</button>
												</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
					</div>

					<!-- Bilgi kartı -->
					<div
						class="mt-4 rounded-xl border border-amber-200/60 bg-amber-50/60 px-4 py-3 text-xs text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-400"
					>
						<strong>Not:</strong> Oluşturulan şubeler ilgili akademisyenin "Şubelerim" listesinde otomatik
						olarak görünür. Öğrenciler ders kaydı aşamasında bu şubelere kayıt yaptırabilir.
					</div>
				</div>
			</div>

			<!-- ============================================================ -->
			<!-- AKADEMİK TAKVİM                                              -->
			<!-- ============================================================ -->
		{:else if apiKey === 'calendar'}
			<div
				class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="mb-4 flex flex-wrap items-center gap-3">
					<span class="font-semibold">Akademik takvim</span>
					{#if terms.length}
						<label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
							<span class="text-xs font-semibold text-slate-500">Dönem</span>
							<select
								bind:value={calendarTermId}
								on:change={reloadCalendarEvents}
								class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5"
							>
								{#each terms as tm}
									<option value={tm.id}>{tm.name}{tm.is_active ? ' (Aktif)' : ''}</option>
								{/each}
							</select>
						</label>
					{/if}
				</div>
				{#if !calendarEvents.length}
					<div class="py-8 text-center text-sm text-slate-400">
						Bu dönem için takvim kaydı yok. Veriler veritabanındaki obs_calendar_events tablosundan
						gelir.
					</div>
				{:else}
					{#if editingCalEventId}
						<div
							class="mb-4 rounded-lg border border-sky-200 bg-sky-50/60 p-4 dark:border-sky-900/40 dark:bg-sky-950/25"
						>
							<div class="mb-3 text-xs font-bold text-slate-600 dark:text-slate-300">
								Takvim kaydı düzenle
							</div>
							<div class="grid gap-3 sm:grid-cols-2">
								<label class="block sm:col-span-2">
									<div class="mb-1 text-xs font-semibold text-slate-500">Başlık</div>
									<input
										bind:value={calEditForm.title}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
									/>
								</label>
								<label class="block">
									<div class="mb-1 text-xs font-semibold text-slate-500">Tür</div>
									<input
										bind:value={calEditForm.event_type}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
									/>
								</label>
								<label class="block">
									<div class="mb-1 text-xs font-semibold text-slate-500">Başlangıç</div>
									<input
										type="date"
										bind:value={calEditForm.start_date}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
									/>
								</label>
								<label class="block">
									<div class="mb-1 text-xs font-semibold text-slate-500">Bitiş</div>
									<input
										type="date"
										bind:value={calEditForm.end_date}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
									/>
								</label>
							</div>
							<div class="mt-3 flex flex-wrap gap-2">
								<button
									type="button"
									on:click={cancelCalEdit}
									class="rounded-lg border border-black/10 px-4 py-2 text-sm font-semibold text-slate-600 dark:border-white/10"
								>
									İptal
								</button>
								<button
									type="button"
									on:click={saveCalCatalogEdit}
									class="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400"
								>
									Kaydet
								</button>
							</div>
						</div>
					{/if}
					{#each calendarEvents as ev, i}
						<div
							class="flex flex-wrap items-center justify-between gap-4 border-t border-black/5 py-3 dark:border-white/10"
						>
							<div class="flex min-w-0 flex-1 flex-wrap items-center gap-4">
								<div
									class="min-w-[10rem] shrink-0 text-xs font-mono text-slate-500 dark:text-slate-400"
								>
									{fmtCalDate(ev.start_date)} – {fmtCalDate(ev.end_date)}
								</div>
								<span
									class="rounded-full px-2.5 py-0.5 text-xs font-medium {CAL_EVENT_STYLES[
										i % CAL_EVENT_STYLES.length
									]}"
								>
									{ev.title || ev.event_type || 'Etkinlik'}
								</span>
								{#if ev.event_type}<span class="text-xs text-slate-400">{ev.event_type}</span>{/if}
							</div>
							<div class="flex shrink-0 gap-1">
								<button
									type="button"
									on:click={() => startCalEdit(ev)}
									class="rounded-lg border border-sky-200 px-2.5 py-1 text-xs font-semibold text-sky-600 dark:border-sky-900/40 dark:text-sky-400"
								>
									Düzenle
								</button>
								<button
									type="button"
									on:click={() => removeCalendarEventRow(ev.id)}
									class="rounded-lg border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-600 dark:border-red-900/40 dark:text-red-400"
								>
									Sil
								</button>
							</div>
						</div>
					{/each}
				{/if}
			</div>

			<!-- ============================================================ -->
			<!-- KAYIT KURALLARI                                               -->
			<!-- ============================================================ -->
		{:else if apiKey === 'reg-rules'}
			<div class="space-y-4">
			{#if termCalSaved}
				<div
					class="mx-auto max-w-lg rounded-lg bg-emerald-50 px-4 py-2 text-center text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
				>
					Dönem takvimi güncellendi (obs_terms kayıt / ekle-bırak alanları).
				</div>
			{/if}
			<div
				class="mx-auto max-w-lg rounded-xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="mb-5 font-bold">Kayıt Kuralları</div>
				<button
					type="button"
					on:click={() => {
						syncTermCalFromSelected();
						showTermCalModal = true;
					}}
					class="mb-4 w-full rounded-lg border border-violet-200 bg-violet-50 py-2.5 text-sm font-semibold text-violet-900 hover:bg-violet-100 dark:border-violet-900/50 dark:bg-violet-950/40 dark:text-violet-100 dark:hover:bg-violet-900/30"
				>
					Ders kayıt / ekle-bırak tarihleri — obs_terms
				</button>
				{#if terms.length}
					<label class="mb-4 block">
						<div class="mb-1 text-xs font-semibold text-slate-500">Dönem</div>
						<select
							bind:value={regRulesTermId}
							on:change={async () => {
								const token = localStorage.token ?? null;
								if (!token || !regRulesTermId) return;
								try {
									const row = await getDouAdminRegistrationSettings(token, regRulesTermId);
									if (row && typeof row === 'object' && Object.keys(row as object).length) {
										applyRegistrationRow(row as Record<string, unknown>);
									}
								} catch {
									/* ignore */
								}
							}}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
						>
							{#each terms as tm}
								<option value={tm.id}>{tm.name}{tm.is_active ? ' (Aktif)' : ''}</option>
							{/each}
						</select>
					</label>
				{/if}
				{#if regSaved}<div
						class="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
					>
						Kaydedildi.
					</div>{/if}
				<div class="space-y-4">
					{#each [['AKTS Limiti (varsayılan)', 'akts_limit_default', 'number'], ['AKTS Limiti (orta GNO)', 'akts_limit_high', 'number'], ['AKTS Limiti (üst GNO / tavan)', 'akts_limit_top', 'number'], ['AKTS Limiti (hazırlık)', 'akts_limit_prep', 'number'], ['Orta kademe için min. GNO', 'min_gpa_for_high_akts', 'number'], ['Üst kademe için min. GNO', 'min_gpa_for_top_akts', 'number'], ['Ekle/Bırak süresi (gün)', 'add_drop_deadline_days', 'number']] as [lbl, field, type]}
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">{lbl}</div>
							<input
								{type}
								bind:value={regRules[field as keyof typeof regRules]}
								step="0.01"
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
							/>
						</label>
					{/each}
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">
							Ders kayıt son tarihi (obs_registration_settings.enrollment_deadline)
						</div>
						<input
							type="date"
							bind:value={regRules.enrollment_deadline}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
						/>
					</label>
					<label class="block">
						<div class="mb-1 text-xs font-semibold text-slate-500">
							Ekle/bırak son tarihi (add_drop_deadline)
						</div>
						<input
							type="date"
							bind:value={regRules.add_drop_deadline}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
						/>
					</label>
					<label class="flex items-center gap-3">
						<input
							type="checkbox"
							bind:checked={regRules.registration_open}
							class="accent-sky-500"
						/>
						<span class="text-sm font-medium">Ders kaydı açık</span>
					</label>
					<button
						on:click={saveRegRules}
						type="button"
						class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
					>
						Kaydet
					</button>
				</div>
			</div>

			{#if showTermCalModal}
				<div
					class="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
					role="dialog"
					aria-modal="true"
				>
					<div
						class="max-h-[92vh] w-full max-w-md overflow-y-auto rounded-2xl border border-black/10 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-slate-900"
					>
						<h2 class="mb-1 text-base font-bold text-slate-800 dark:text-slate-100">
							Dönem: {terms.find((t) => t.id === regRulesTermId)?.name ?? '—'}
						</h2>
						<p class="mb-4 text-xs text-slate-500">
							<strong>obs_terms</strong>: registration_* = normal ders kayıt penceresi; add_drop_* =
							ekle-bırak. Öğrenci taslak ekleme / gönderim bu tarihlere göre kısıtlanır.
						</p>
						<div class="space-y-3 border-b border-black/5 pb-4 dark:border-white/10">
							<label class="flex items-center gap-2 text-sm font-medium">
								<input type="checkbox" bind:checked={termCalForm.registration_open} class="accent-sky-500" />
								Ders kayıt açık (registration_open)
							</label>
							<label class="block text-xs">
								<span class="font-semibold text-slate-600 dark:text-slate-400">Başlangıç</span>
								<input
									type="date"
									bind:value={termCalForm.registration_start}
									class="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
								/>
							</label>
							<label class="block text-xs">
								<span class="font-semibold text-slate-600 dark:text-slate-400">Bitiş</span>
								<input
									type="date"
									bind:value={termCalForm.registration_end}
									class="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
								/>
							</label>
						</div>
						<div class="mt-4 space-y-3">
							<label class="flex items-center gap-2 text-sm font-medium">
								<input type="checkbox" bind:checked={termCalForm.add_drop_open} class="accent-sky-500" />
								Ekle/bırak açık (add_drop_open)
							</label>
							<label class="block text-xs">
								<span class="font-semibold text-slate-600 dark:text-slate-400">Ekle/bırak başlangıç</span>
								<input
									type="date"
									bind:value={termCalForm.add_drop_start}
									class="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
								/>
							</label>
							<label class="block text-xs">
								<span class="font-semibold text-slate-600 dark:text-slate-400">Ekle/bırak bitiş</span>
								<input
									type="date"
									bind:value={termCalForm.add_drop_end}
									class="mt-1 w-full rounded-lg border border-black/10 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5"
								/>
							</label>
						</div>
						<div class="mt-6 flex gap-2">
							<button
								type="button"
								on:click={() => (showTermCalModal = false)}
								class="flex-1 rounded-lg border border-black/10 py-2 text-sm font-semibold dark:border-white/10"
								>İptal</button
							>
							<button
								type="button"
								disabled={termCalSaving}
								on:click={saveTermCalWindows}
								class="flex-1 rounded-lg bg-violet-600 py-2 text-sm font-bold text-white hover:bg-violet-500 disabled:opacity-50"
								>{termCalSaving ? 'Kaydediliyor…' : 'Kaydet'}</button
							>
						</div>
					</div>
				</div>
			{/if}
			</div>
		{:else if apiKey === 'doc-process'}
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">Belge Türü</th>
								<th class="px-4 py-3 text-left">Tip</th>
								<th class="px-4 py-3 text-left">Kurum</th>
								<th class="px-4 py-3 text-left">Tarih</th>
								<th class="px-4 py-3 text-center">Durum</th>
								<th class="px-4 py-3"></th>
							</tr>
						</thead>
						<tbody>
							{#each docRequests as { id: string; document_type: string; document_subtype: string; requesting_institution: string; created_at: string; status: string }[] as req}
								<tr class="border-t border-black/5 dark:border-white/10">
									<td class="px-4 py-3 font-medium">{req.document_type}</td>
									<td class="px-4 py-3 text-slate-500">{req.document_subtype}</td>
									<td class="px-4 py-3 text-xs text-slate-500">{req.requesting_institution}</td>
									<td class="px-4 py-3 text-xs text-slate-400">{req.created_at?.slice(0, 10)}</td>
									<td class="px-4 py-3 text-center">
										<span
											class="rounded-full px-2.5 py-0.5 text-xs font-medium {req.status ===
											'tamamlandı'
												? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
												: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}"
										>
											{req.status}
										</span>
									</td>
									<td class="px-4 py-3 text-right">
										{#if req.status !== 'tamamlandı'}
											<button
												on:click={() => completeDoc(req.id)}
												type="button"
												class="rounded-lg bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-400 transition-colors"
											>
												Tamamla
											</button>
										{/if}
									</td>
								</tr>
							{:else}
								<tr
									><td colspan="6" class="px-4 py-8 text-center text-sm text-slate-400"
										>Belge talebi yok.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			<!-- ============================================================ -->
			<!-- GLOBAL DUYURU                                                 -->
			<!-- ============================================================ -->
		{:else if apiKey === 'announce'}
			<div class="mx-auto max-w-3xl space-y-6">
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-slate-800 dark:text-slate-100">
						{annEditId ? 'Duyuru Düzenle' : 'Global Duyuru Oluştur'}
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
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
							/>
						</label>
						<label class="block">
							<div class="mb-1 text-xs font-semibold text-slate-500">İçerik</div>
							<textarea
								bind:value={annForm.content}
								rows="5"
								class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
							></textarea>
						</label>
						<div>
							<div class="mb-1.5 text-xs font-semibold text-slate-500">Hedef kitle</div>
							<div class="grid grid-cols-2 gap-2">
								<button
									type="button"
									on:click={() => {
										annForm.audience_type = 'all';
										annForm.department_id = '';
									}}
									class="rounded-lg border px-3 py-2.5 text-xs font-medium transition-colors
										{annForm.audience_type === 'all'
										? 'border-sky-400 bg-sky-50 text-sky-700 dark:border-sky-500 dark:bg-sky-900/30 dark:text-sky-300'
										: 'border-black/10 bg-white text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5'}"
								>
									Tüm kullanıcılar
								</button>
								<button
									type="button"
									on:click={() => {
										annForm.audience_type = 'department';
									}}
									class="rounded-lg border px-3 py-2.5 text-xs font-medium transition-colors
										{annForm.audience_type === 'department'
										? 'border-sky-400 bg-sky-50 text-sky-700 dark:border-sky-500 dark:bg-sky-900/30 dark:text-sky-300'
										: 'border-black/10 bg-white text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5'}"
								>
									Belirli bölüm
								</button>
							</div>
						</div>
						{#if annForm.audience_type === 'department'}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Bölüm</div>
								<select
									bind:value={annForm.department_id}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-white/5"
								>
									<option value="">— Bölüm seçin —</option>
									{#each departments as d}
										<option value={d.id}>{d.code} — {d.name}</option>
									{/each}
								</select>
							</label>
						{/if}
						{#if annEditId}
							<label
								class="flex cursor-pointer items-center gap-2 text-sm text-slate-600 dark:text-slate-300"
							>
								<input type="checkbox" bind:checked={annIsActive} class="rounded border-black/20" />
								Aktif (yayında görünsün)
							</label>
						{/if}
						<div class="flex flex-col gap-2 sm:flex-row sm:items-stretch">
							{#if annEditId}
								<button
									type="button"
									on:click={cancelAnnEdit}
									class="w-full rounded-lg border border-black/10 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10 sm:w-auto sm:px-6"
								>
									İptal
								</button>
							{/if}
							<button
								on:click={publishAnnounce}
								disabled={annPublishing}
								type="button"
								class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors sm:flex-1"
							>
								{annPublishing
									? 'Gönderiliyor…'
									: annEditId
										? 'Kaydet'
										: 'Yayınla'}
							</button>
						</div>
					</div>
				</div>

				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-3 font-semibold text-slate-800 dark:text-slate-100">Tüm duyurular</div>
					{#each adminAnnouncements as a}
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
										on:click={() => startAnnEdit(a)}
										class="rounded-lg border border-black/10 px-2.5 py-1 text-xs font-semibold text-sky-600 hover:bg-sky-50 dark:border-white/10 dark:text-sky-400 dark:hover:bg-sky-950/30"
									>
										Düzenle
									</button>
									<button
										type="button"
										on:click={() => removeAdminAnn(a.id)}
										class="rounded-lg border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 dark:border-red-900/40 dark:text-red-400 dark:hover:bg-red-950/20"
									>
										Sil
									</button>
								</div>
							</div>
							<div class="mt-1 text-xs text-slate-400">
								{a.audience_type}
								{#if a.created_by_name}
									{' · '}{a.created_by_name}
								{/if}
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
						<div class="py-8 text-center text-sm text-slate-400">Kayıtlı duyuru yok.</div>
					{/each}
				</div>
			</div>

			<!-- ============================================================ -->
			<!-- AUDİT KAYITLARI                                               -->
			<!-- ============================================================ -->
		{:else if apiKey === 'audit'}
			<div
				class="overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead
							class="bg-slate-50 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
						>
							<tr>
								<th class="px-4 py-3 text-left">#</th>
								<th class="px-4 py-3 text-left">Eylem</th>
								<th class="px-4 py-3 text-left">Varlık</th>
								<th class="px-4 py-3 text-left">Kullanıcı</th>
								<th class="px-4 py-3 text-left">Tarih</th>
							</tr>
						</thead>
						<tbody>
							{#each auditLogs as { id: string; action: string; entity_type: string; user: string; created_at: string }[] as log}
								<tr
									class="border-t border-black/5 dark:border-white/10 hover:bg-slate-50/50 transition-colors"
								>
									<td class="px-4 py-3 font-mono text-xs text-slate-400">{log.id}</td>
									<td class="px-4 py-3">
										<span
											class="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600 dark:bg-white/10 dark:text-slate-300"
											>{log.action}</span
										>
									</td>
									<td class="px-4 py-3 font-mono text-xs text-slate-500">{log.entity_type}</td>
									<td class="px-4 py-3 text-xs font-medium">{log.user}</td>
									<td class="px-4 py-3 text-xs text-slate-400"
										>{log.created_at?.slice(0, 16).replace('T', ' ')}</td
									>
								</tr>
							{:else}
								<tr
									><td colspan="5" class="px-4 py-8 text-center text-sm text-slate-400"
										>Log bulunamadı.</td
									></tr
								>
							{/each}
						</tbody>
					</table>
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
