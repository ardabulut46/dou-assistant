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
		type AdminUser,
		type AdminRole,
		type AdminInstructor,
		type DouDepartment,
		type DouTerm,
		type DouCourse,
		type DouClassroom,
		type DouCalendarEvent,
		type DouAnnouncement
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
	let newUser = { email: '', full_name: '', role: 'user', password: '' };
	let userCreating = false;

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
			users: (t) =>
				getDouAdminUsers(t, {
					role: userRoleFilter || undefined,
					search: userSearch || undefined
				}).then((r) => {
					users = r.users;
				}),
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
				})
		};
		try {
			await (loaders[apiKey]?.(token) ?? Promise.resolve());
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'API hatası.';
		} finally {
			loading = false;
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
		loadErr = null;
		const token = localStorage.token ?? null;
		if (!token) {
			userCreating = false;
			return;
		}
		try {
			await createDouAdminUser(token, { ...newUser });
			showUserModal = false;
			newUser = { email: '', full_name: '', role: 'user', password: '' };
			const r = await getDouAdminUsers(token, {
				role: userRoleFilter || undefined,
				search: userSearch || undefined
			});
			users = r.users ?? [];
		} catch (e: unknown) {
			loadErr = e instanceof Error ? e.message : 'Kullanıcı oluşturulamadı.';
		} finally {
			userCreating = false;
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
					on:click={() => (showUserModal = true)}
					type="button"
					class="ml-auto rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
				>
					+ Kullanıcı Ekle
				</button>
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
										<button
											on:click={() => toggleUserActive(u)}
											type="button"
											class="rounded-lg border border-black/10 px-2 py-1 text-xs hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5 transition-colors"
										>
											{u.is_active ? 'Dondur' : 'Aktifleştir'}
										</button>
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

			<!-- Yeni kullanıcı modal -->
			{#if showUserModal}
				<div
					class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
				>
					<div
						class="w-full max-w-md rounded-2xl border border-black/10 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-slate-900"
					>
						<div class="mb-5 flex items-center justify-between">
							<div class="font-bold">Yeni Kullanıcı</div>
							<button
								on:click={() => (showUserModal = false)}
								type="button"
								class="text-slate-400 hover:text-slate-700">✕</button
							>
						</div>
						<div class="space-y-3">
							{#each [['Ad Soyad', 'full_name', 'text'], ['E-posta', 'email', 'email'], ['Parola', 'password', 'password']] as [lbl, field, type]}
								<label class="block">
									<div class="mb-1 text-xs font-semibold text-slate-500">{lbl}</div>
									<input
										bind:value={newUser[field as keyof typeof newUser]}
										{type}
										class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-slate-800"
									/>
								</label>
							{/each}
							<label class="block">
								<div class="mb-1 text-xs font-semibold text-slate-500">Rol</div>
								<select
									bind:value={newUser.role}
									class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none dark:border-white/10 dark:bg-slate-800"
								>
									{#each ADMIN_USER_ROLE_OPTIONS.filter((r) => r.value !== 'pending') as ro}
										<option value={ro.value}>{ro.label} — {ro.value}</option>
									{/each}
								</select>
								<p class="mt-1 text-[11px] leading-snug text-slate-400">
									Veritabanı değerleri: user, academician, admin; onay bekleyenler için ayrıca pending.
								</p>
							</label>
							<div class="flex gap-2 pt-2">
								<button
									on:click={createUser}
									disabled={userCreating}
									type="button"
									class="flex-1 rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50"
								>
									{userCreating ? 'Oluşturuluyor…' : 'Oluştur'}
								</button>
								<button
									on:click={() => (showUserModal = false)}
									type="button"
									class="rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"
								>
									İptal
								</button>
							</div>
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
