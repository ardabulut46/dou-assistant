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
		getDouTerms,
		createDouTerm,
		getDouCourses,
		createDouCourse,
		getDouClassrooms,
		createDouClassroom,
		getDouAdminDocumentRequests,
		completeDouDocumentRequest,
		getDouAdminAuditLogs,
		getDouAdminInstructors,
		getDouAdminSections,
		createDouAdminSection,
		getDouAdminCalendarEvents,
		getDouAdminRegistrationSettings,
		postDouAdminRegistrationSettings,
		createDouAdminAnnouncement,
		type AdminUser,
		type AdminRole,
		type AdminInstructor,
		type DouDepartment,
		type DouTerm,
		type DouCourse,
		type DouClassroom,
		type DouCalendarEvent
	} from '$lib/apis/douAcademic';

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

	$: activePath = `/obs/admin/${$page.params.path ?? ''}`;
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
	let newUser = { email: '', full_name: '', role: 'Öğrenci', password: '' };
	let userCreating = false;
	let editUserId = '';
	let editUserRole = '';
	let editUserActive = true;

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

	let annForm = { title: '', content: '', audience_type: 'all' };
	let annSaved = false;
	let annErr: string | null = null;
	let annPublishing = false;
	let regRules = {
		akts_limit_default: 30,
		akts_limit_high: 36,
		akts_limit_prep: 25,
		min_gpa_for_high_akts: 2.5,
		registration_open: true,
		add_drop_deadline_days: 14
	};
	let regSaved = false;
	let regRulesTermId = '';
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
		if (row.max_akts != null) regRules.akts_limit_default = Number(row.max_akts);
		if (row.bonus_akts != null) {
			const base = row.max_akts != null ? Number(row.max_akts) : regRules.akts_limit_default;
			regRules.akts_limit_high = base + Number(row.bonus_akts);
		}
		if (row.gpa_threshold != null) regRules.min_gpa_for_high_akts = Number(row.gpa_threshold);
		if (row.akts_limit_prep != null) regRules.akts_limit_prep = Number(row.akts_limit_prep);
		if (row.registration_open != null) regRules.registration_open = Boolean(row.registration_open);
		if (row.add_drop_deadline_days != null)
			regRules.add_drop_deadline_days = Number(row.add_drop_deadline_days);
	}

	// Generic create forms
	let deptForm = { code: '', name: '' };
	let termForm = {
		name: '',
		academic_year: '2025-2026',
		season: 'spring',
		starts_at: '',
		ends_at: ''
	};
	let courseForm = { code: '', name: '', credits: 3, akts: 5, department_id: '' };
	let classForm = { code: '', name: '', capacity: 30, building: '', floor: 0 };
	let formSaved: Record<string, boolean> = {};

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

	async function loadPage(path: string) {
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
			courses: (t) =>
				getDouCourses(t).then((r) => {
					courses = r;
				}),
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
			announce: async () => {
				annErr = null;
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

	async function saveRegRules() {
		regSaved = false;
		const token = localStorage.token ?? null;
		if (!token) return;
		try {
			const maxAkts = regRules.akts_limit_default;
			const bonusAkts = Math.max(0, regRules.akts_limit_high - regRules.akts_limit_default);
			await postDouAdminRegistrationSettings(
				token,
				{
					max_akts: maxAkts,
					bonus_akts: bonusAkts,
					gpa_threshold: regRules.min_gpa_for_high_akts,
					enrollment_deadline: '',
					add_drop_deadline: String(regRules.add_drop_deadline_days)
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

	async function publishAnnounce() {
		annErr = null;
		annSaved = false;
		const token = localStorage.token ?? null;
		if (!token || !annForm.title.trim() || !annForm.content.trim()) {
			annErr = 'Başlık ve içerik zorunludur.';
			return;
		}
		annPublishing = true;
		try {
			await createDouAdminAnnouncement(token, {
				title: annForm.title.trim(),
				content: annForm.content.trim(),
				audience_type: annForm.audience_type || 'all'
			});
			annSaved = true;
			annForm = { title: '', content: '', audience_type: 'all' };
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
		void loadPage(activePath);
	});

	async function createUser() {
		userCreating = true;
		loadErr = null;
		const token = localStorage.token ?? null;
		try {
			const u = await createDouAdminUser(token, { ...newUser });
			users = [...users, u];
			showUserModal = false;
			newUser = { email: '', full_name: '', role: 'Öğrenci', password: '' };
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
		const updated = await patchDouAdminUser(token, u.id, { role }).catch(() => u);
		users = users.map((x) => (x.id === u.id ? updated : x));
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
			setTimeout(() => (sectionSaved = false), 3500);
		} catch (e: unknown) {
			sectionErr = e instanceof Error ? e.message : 'Şube oluşturulamadı.';
		} finally {
			sectionSaving = false;
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

	async function genericCreate(formType: string) {
		const token = localStorage.token ?? null;
		loadErr = null;
		try {
			if (formType === 'dept') await createDouDepartment(token, deptForm);
			if (formType === 'term') await createDouTerm(token, termForm);
			if (formType === 'course') await createDouCourse(token, courseForm);
			if (formType === 'class') await createDouClassroom(token, classForm);
			formSaved[formType] = true;
			await loadPage(activePath);
		} catch (e: unknown) {
			formSaved[formType] = false;
			loadErr = e instanceof Error ? e.message : 'Kayıt eklenemedi.';
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
					on:input={() => loadPage(activePath)}
					placeholder="Ad veya e-posta ara…"
					class="w-56 rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
				/>
				<select
					bind:value={userRoleFilter}
					on:change={() => loadPage(activePath)}
					class="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-sm outline-none dark:border-white/10 dark:bg-white/5"
				>
					<option value="">Tüm Roller</option>
					<option value="Öğrenci">Öğrenci</option>
					<option value="Akademisyen">Akademisyen</option>
					<option value="Admin">Admin</option>
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
											class="rounded-lg border border-black/10 bg-white px-2 py-1 text-xs outline-none dark:border-white/10 dark:bg-white/5"
										>
											<option value="Öğrenci">Öğrenci</option>
											<option value="Akademisyen">Akademisyen</option>
											<option value="Admin">Admin</option>
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
									<option value="Öğrenci">Öğrenci</option>
									<option value="Akademisyen">Akademisyen</option>
									<option value="Admin">Admin</option>
								</select>
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
						class="grid grid-cols-3 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
					>
						<div>Kod</div>
						<div class="col-span-2">Ad</div>
					</div>
					{#each departments as d}
						<div
							class="grid grid-cols-3 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10"
						>
							<div class="font-mono font-semibold text-slate-500">{d.code}</div>
							<div class="col-span-2">{d.name}</div>
						</div>
					{:else}<div class="px-5 py-8 text-center text-sm text-slate-400">Kayıt yok.</div>{/each}
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-sm">Yeni Bölüm</div>
					{#if formSaved['dept']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Eklendi.
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
						<button
							on:click={() => genericCreate('dept')}
							type="button"
							class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
							>Ekle</button
						>
					</div>
				</div>
			</div>
		{:else if apiKey === 'terms'}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<div
					class="col-span-2 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div
						class="grid grid-cols-4 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
					>
						<div class="col-span-2">Dönem</div>
						<div>Başlangıç</div>
						<div>Bitiş</div>
					</div>
					{#each terms as t}
						<div
							class="grid grid-cols-4 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10"
						>
							<div class="col-span-2 font-medium">
								{t.name}
								{#if t.is_active}<span
										class="ml-2 rounded-full bg-sky-100 px-1.5 py-0.5 text-[10px] font-bold text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
										>Aktif</span
									>{/if}
							</div>
							<div class="text-xs text-slate-400">{t.starts_at}</div>
							<div class="text-xs text-slate-400">{t.ends_at}</div>
						</div>
					{:else}<div class="px-5 py-8 text-center text-sm text-slate-400">Dönem yok.</div>{/each}
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-sm">Yeni Dönem</div>
					{#if formSaved['term']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Eklendi.
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
						<button
							on:click={() => genericCreate('term')}
							type="button"
							class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
							>Ekle</button
						>
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
									></tr
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
									</tr>
								{:else}<tr
										><td colspan="4" class="px-4 py-8 text-center text-sm text-slate-400"
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
					<div class="mb-4 font-semibold text-sm">Yeni Ders</div>
					{#if formSaved['course']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Eklendi.
						</div>{/if}
					<div class="space-y-3">
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
						<button
							on:click={() => genericCreate('course')}
							type="button"
							class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
							>Ekle</button
						>
					</div>
				</div>
			</div>
		{:else if apiKey === 'classrooms'}
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
				<div
					class="col-span-2 overflow-hidden rounded-xl border border-black/10 bg-white shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div
						class="grid grid-cols-4 bg-slate-50 px-5 py-3 text-xs font-bold text-slate-500 dark:bg-white/5 dark:text-slate-400"
					>
						<div>Kod</div>
						<div class="col-span-2">Ad</div>
						<div>Kapasite</div>
					</div>
					{#each classrooms as c}
						<div
							class="grid grid-cols-4 border-t border-black/5 px-5 py-3 text-sm dark:border-white/10"
						>
							<div class="font-mono font-semibold text-slate-500">{c.code}</div>
							<div class="col-span-2">{c.name}</div>
							<div class="text-slate-500">{c.capacity}</div>
						</div>
					{:else}<div class="px-5 py-8 text-center text-sm text-slate-400">Derslik yok.</div>{/each}
				</div>
				<div
					class="rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
				>
					<div class="mb-4 font-semibold text-sm">Yeni Derslik</div>
					{#if formSaved['class']}<div
							class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
						>
							Eklendi.
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
						<button
							on:click={() => genericCreate('class')}
							type="button"
							class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 transition-colors"
							>Ekle</button
						>
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
							<span class="font-bold text-slate-800 dark:text-slate-100">Yeni Şube Aç</span>
						</div>

						{#if sectionSaved}
							<div
								class="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
							>
								✓ Şube başarıyla oluşturuldu.
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

							<button
								on:click={createSection}
								disabled={sectionSaving}
								type="button"
								class="w-full rounded-lg bg-sky-500 py-2.5 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
							>
								{sectionSaving ? 'Oluşturuluyor…' : 'Şubeyi Oluştur'}
							</button>
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
					{#each calendarEvents as ev, i}
						<div
							class="flex flex-wrap items-center gap-4 border-t border-black/5 py-3 dark:border-white/10"
						>
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
					{/each}
				{/if}
			</div>

			<!-- ============================================================ -->
			<!-- KAYIT KURALLARI                                               -->
			<!-- ============================================================ -->
		{:else if apiKey === 'reg-rules'}
			<div
				class="mx-auto max-w-lg rounded-xl border border-black/10 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="mb-5 font-bold">Kayıt Kuralları</div>
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
					{#each [['AKTS Limiti (varsayılan)', 'akts_limit_default', 'number'], ['AKTS Limiti (yüksek GNO)', 'akts_limit_high', 'number'], ['AKTS Limiti (hazırlık)', 'akts_limit_prep', 'number'], ['Yüksek AKTS için min. GNO', 'min_gpa_for_high_akts', 'number'], ['Ekle/Bırak süresi (gün)', 'add_drop_deadline_days', 'number']] as [lbl, field, type]}
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

			<!-- ============================================================ -->
			<!-- BELGE TALEBİ İŞLEME                                          -->
			<!-- ============================================================ -->
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
			<div
				class="mx-auto max-w-lg rounded-xl border border-black/10 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-white/5"
			>
				<div class="mb-4 font-semibold">Global Duyuru Oluştur</div>
				{#if annSaved}<div
						class="mb-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
					>
						Duyuru veritabanına kaydedildi.
					</div>{/if}
				{#if annErr}<div
						class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400"
					>
						{annErr}
					</div>{/if}
				<div class="space-y-3">
					<label class="block"
						><div class="mb-1 text-xs font-semibold text-slate-500">Başlık</div>
						<input
							bind:value={annForm.title}
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
						/></label
					>
					<label class="block"
						><div class="mb-1 text-xs font-semibold text-slate-500">İçerik</div>
						<textarea
							bind:value={annForm.content}
							rows="5"
							class="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-400/40 dark:border-white/10 dark:bg-white/5"
						></textarea></label
					>
					<div
						class="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-600 dark:bg-amber-950/20 dark:text-amber-400"
					>
						Bu duyuru tüm kullanıcılara gönderilecek. Kitle: all
					</div>
					<button
						on:click={publishAnnounce}
						disabled={annPublishing}
						type="button"
						class="w-full rounded-lg bg-sky-500 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50 transition-colors"
					>
						{annPublishing ? 'Gönderiliyor…' : 'Yayınla'}
					</button>
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
