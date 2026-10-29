<?php

/**
 * PHPUnit bootstrap for the AttendanceeController verifier.
 *
 * Every test boots the real application under test from APP_DIR (/app, with the agent's changes
 * applied): its own bootstrap/app.php, configuration, service providers, Eloquent models, facades
 * and helpers, through Laravel's own testing base class. Each test gets a fresh in-memory SQLite
 * database built by the app's own migrations (see migrateDatabase()). The suites drive the
 * controller's public actions, the methods routes/api.php maps the attendance endpoints onto,
 * resolved and called through the container the way the router calls them, and read the results
 * back from the JSON responses and the database.
 */

namespace {
    require (getenv('APP_DIR') ?: '/app').'/vendor/autoload.php';
}

namespace Tests\Verifier {

    use App\Http\Controllers\admin\AttendanceeController;
    use App\Models\User;
    use Carbon\Carbon;
    use Illuminate\Contracts\Auth\Authenticatable;
    use Illuminate\Contracts\Http\Kernel as HttpKernel;
    use Illuminate\Database\Eloquent\Model;
    use Illuminate\Database\Schema\Blueprint;
    use Illuminate\Foundation\Testing\TestCase;
    use Illuminate\Http\JsonResponse;
    use Illuminate\Http\Request;
    use Illuminate\Support\Facades\DB;
    use Illuminate\Support\Facades\Schema;
    use Laravel\Passport\Passport;

    abstract class AttendanceEndpointTestCase extends TestCase
    {
        /** The signed-in administrator every suite acts as unless a test says otherwise. */
        public const ADMIN_ID = 1;

        /** Every seeded employee shares this branch so the admin's branch scope sees them all. */
        public const BRANCH_ID = 1;

        /** Frozen wall clock, in Asia/Kolkata (the app's timezone), so `today()` never varies per run. */
        public const FROZEN_NOW = '2026-01-20 11:00:00';

        /**
         * Migrations that change other tables with MySQL-only DDL (MODIFY, dropping foreign keys,
         * column changes that need doctrine/dbal). SQLite cannot run them, and none of them changes
         * a column the attendance code reads, so they are skipped.
         */
        private const MYSQL_ONLY_MIGRATIONS = [
            '2026_05_27_200000_change_quotation_status_type_in_orders_table.php',
            '2026_05_27_210000_change_purchase_status_columns_nullable_string.php',
            '2026_05_27_223000_drop_staff_id_foreign_from_advance_payments_table.php',
            '2026_05_27_230500_drop_credit_note_item_foreign_keys.php',
            '2026_05_27_231000_drop_custom_invoice_item_foreign_keys.php',
            '2026_05_27_232000_drop_multiple_foreign_keys.php',
            '2026_05_27_233000_drop_product_foreign_and_barcode_unique_indexes.php',
            '2026_05_27_235000_change_sunday_off_to_nullable_varchar_in_settings_table.php',
        ];

        /**
         * These two are dated before the migration that creates the `attendance` table, so on an
         * empty database they find no table and do nothing. Production's table predates them and
         * carries their columns, so they run again once the table exists.
         */
        private const EARLY_ATTENDANCE_MIGRATIONS = [
            '2026_04_21_130000_add_check_location_fields_to_attendance_table.php',
            '2026_04_21_140000_add_check_ip_fields_to_attendance_table.php',
        ];

        /** The models the attendance code reads and writes through. */
        private const MODELS = [
            \App\Models\Attendance::class,
            \App\Models\CompanyRulesModel::class,
            \App\Models\HolidayCalendarModel::class,
            \App\Models\LeaveModel::class,
            \App\Models\Setting::class,
            \App\Models\User::class,
        ];

        private static ?string $runtimeDir = null;

        /** @var array<string, object> one object per migration file, loaded once per run */
        private static array $migrations = [];

        public function createApplication()
        {
            $runtimeDir = self::runtimeDir();

            $app = require (getenv('APP_DIR') ?: '/app').'/bootstrap/app.php';

            // A deployed install has its public/storage link, so the AppServiceProvider does not
            // try to create one while booting.
            $app->usePublicPath($runtimeDir.'/public');
            $app->make(HttpKernel::class)->bootstrap();

            // The request in place before any action runs; each action call swaps in its own.
            $app->instance('request', Request::create('http://localhost/'));
            Passport::loadKeysFrom($runtimeDir);

            return $app;
        }

        /**
         * The environment for the whole run, set once before the first application boots.
         * Everything the framework writes goes to a private temp directory: the suites run as an
         * unprivileged user that cannot write under /app.
         */
        private static function runtimeDir(): string
        {
            if (self::$runtimeDir !== null) {
                return self::$runtimeDir;
            }

            $dir = sys_get_temp_dir().'/attendance-verifier-'.getmypid();
            if (!is_dir($dir.'/public/storage')) {
                mkdir($dir.'/public/storage', 0700, true);
            }
            file_put_contents($dir.'/routes.php', "<?php\n");

            $env = [
                'APP_ENV' => 'testing',
                'APP_KEY' => 'base64:'.base64_encode(str_repeat('v', 32)),
                'APP_URL' => 'http://localhost',
                'DB_CONNECTION' => 'sqlite',
                'DB_DATABASE' => ':memory:',
                'CACHE_DRIVER' => 'array',
                'SESSION_DRIVER' => 'array',
                'QUEUE_CONNECTION' => 'sync',
                'MAIL_MAILER' => 'array',
                'LOG_CHANNEL' => 'null',
                'APP_CONFIG_CACHE' => $dir.'/config.php',
                'APP_EVENTS_CACHE' => $dir.'/events.php',
                'APP_PACKAGES_CACHE' => $dir.'/packages.php',
                'APP_SERVICES_CACHE' => $dir.'/services.php',
                // The suites call the controller's actions directly, so no route file is loaded.
                'APP_ROUTES_CACHE' => $dir.'/routes.php',
            ];
            foreach ($env as $key => $value) {
                putenv("{$key}={$value}");
                $_ENV[$key] = $_SERVER[$key] = $value;
            }

            // Passport's api guard needs its key pair to look at a request nobody has signed in
            // on, so the run gets a pair of its own.
            $key = openssl_pkey_new(['private_key_bits' => 2048, 'private_key_type' => OPENSSL_KEYTYPE_RSA]);
            openssl_pkey_export($key, $privateKey);
            file_put_contents($dir.'/oauth-private.key', $privateKey);
            file_put_contents($dir.'/oauth-public.key', openssl_pkey_get_details($key)['key']);

            register_shutdown_function(static function () use ($dir): void {
                foreach (['config.php', 'events.php', 'packages.php', 'services.php', 'routes.php', 'oauth-private.key', 'oauth-public.key'] as $file) {
                    @unlink($dir.'/'.$file);
                }
                @rmdir($dir.'/public/storage');
                @rmdir($dir.'/public');
                @rmdir($dir);
            });

            return self::$runtimeDir = $dir;
        }

        protected function setUp(): void
        {
            parent::setUp();

            $this->migrateDatabase();
            Carbon::setTestNow(Carbon::parse(self::FROZEN_NOW, 'Asia/Kolkata'));

            $this->actingAs($this->seedUser(self::ADMIN_ID, 'Aaron Admin', 'admin'));
        }

        /**
         * Builds the schema with the app's own migrations, in order, then makes the three
         * adjustments a fresh SQLite database needs: the MySQL-only migrations are skipped, the
         * attendance migrations that predate the table run again, and every table the attendance
         * code uses gets the attributes its model declares that no migration creates (the policy
         * settings on `company_rules`, `checkin_method` on `attendance`, and so on), each as a
         * nullable column of the model's cast type.
         */
        private function migrateDatabase(): void
        {
            $files = glob($this->app->databasePath('migrations').'/*.php');
            sort($files);

            foreach ($files as $file) {
                if (!in_array(basename($file), self::MYSQL_ONLY_MIGRATIONS, true)) {
                    $this->runMigration($file);
                }
            }

            foreach (self::EARLY_ATTENDANCE_MIGRATIONS as $name) {
                $this->runMigration($this->app->databasePath('migrations/'.$name));
            }

            foreach (self::MODELS as $model) {
                $this->addDeclaredColumns(new $model());
            }
        }

        private function runMigration(string $file): void
        {
            (self::$migrations[$file] ??= require $file)->up();
        }

        private function addDeclaredColumns(Model $model): void
        {
            $table = $model->getTable();
            $missing = array_diff($model->getFillable(), Schema::getColumnListing($table));
            if ($missing === []) {
                return;
            }

            $casts = $model->getCasts();
            Schema::table($table, function (Blueprint $blueprint) use ($missing, $casts): void {
                foreach ($missing as $column) {
                    match (explode(':', (string) ($casts[$column] ?? ''))[0]) {
                        'bool', 'boolean' => $blueprint->boolean($column)->nullable(),
                        'int', 'integer' => $blueprint->integer($column)->nullable(),
                        'decimal', 'float', 'double', 'real' => $blueprint->decimal($column, 12, 2)->nullable(),
                        'date' => $blueprint->date($column)->nullable(),
                        'datetime', 'timestamp' => $blueprint->dateTime($column)->nullable(),
                        default => $blueprint->string($column)->nullable(),
                    };
                }
            });
        }

        /** Signs $user in on both guards the controller consults, or signs everybody out for null. */
        public function actingAs(?Authenticatable $user, $guard = null)
        {
            $auth = $this->app['auth'];
            foreach (['web', 'api'] as $name) {
                $auth->guard($name)->forgetUser();
                if ($user !== null) {
                    $auth->guard($name)->setUser($user);
                }
            }

            return $this;
        }

        // --- fixtures -----------------------------------------------------------------------

        protected function seedUser(int $id, string $name, string $role = 'staff'): User
        {
            DB::table('users')->insert([
                'id' => $id,
                'name' => $name,
                'role' => $role,
                'branch_id' => self::BRANCH_ID,
                'isDeleted' => 0,
                'profile_image' => null,
            ]);

            return User::query()->findOrFail($id);
        }

        protected function seedCompanyRules(array $overrides = []): void
        {
            DB::table('company_rules')->insert(array_merge([
                'working_hours_per_day' => 8,
                'lunch_break' => '00:30:00',
            ], $overrides));
        }

        protected function seedSettings(array $overrides = []): void
        {
            DB::table('settings')->insert(array_merge([
                'open_time' => '09:00:00',
                'grace_period' => 10,
            ], $overrides));
        }

        protected function seedApprovedLeave(int $userId, string $startDate, string $endDate): int
        {
            return DB::table('leaves')->insertGetId([
                'user_id' => $userId,
                'start_date' => $startDate,
                'end_date' => $endDate,
                'status' => 'approved',
            ]);
        }

        protected function seedHoliday(string $date, string $title): int
        {
            // The table keeps its original holiday_name/date pair (both required) next to the
            // title/holiday_date pair added later; a real row carries both.
            return DB::table('holiday_calendar')->insertGetId([
                'holiday_name' => $title,
                'date' => $date,
                'title' => $title,
                'holiday_date' => $date,
            ]);
        }

        /** Writes a raw punch row straight into the attendance table (fixture, not an action). */
        protected function seedPunchRow(int $userId, string $date, array $overrides = []): int
        {
            return DB::table('attendance')->insertGetId(array_merge([
                'user_id' => $userId,
                'branch_id' => self::BRANCH_ID,
                'date' => $date,
                'check_in_time' => null,
                'check_out_time' => null,
                'check_in_location_name' => null,
                'check_out_location_name' => null,
                'location' => null,
                'meal_break' => '00:30:00',
                'work_hours' => '00:00:00',
                'overtime' => '00:00:00',
                'status' => null,
                'reason' => null,
                'is_late' => 0,
                'late_minutes' => 0,
            ], $overrides));
        }

        /**
         * Older deployments' attendance tables still carry the location columns the calendar falls
         * back through before the generic `location` column.
         */
        protected function addLegacyLocationColumns(): void
        {
            Schema::table('attendance', function (Blueprint $table): void {
                $table->string('check_in_location')->nullable();
                $table->string('check_out_location')->nullable();
                $table->string('location_name')->nullable();
            });
        }

        // --- HTTP actions -------------------------------------------------------------------

        /**
         * Calls one controller action the way the router does: the request becomes the current
         * request, the controller comes from the container, and the action's parameters are
         * injected (route parameters by name).
         */
        private function callAction(string $action, Request $request, array $routeParameters = []): JsonResponse
        {
            $this->app->instance('request', $request);

            return $this->app->call([$this->app->make(AttendanceeController::class), $action], $routeParameters);
        }

        protected function postUpdateDayRecords(array $payload): JsonResponse
        {
            return $this->callAction('updateDayAttendanceRecords', Request::create('/attendance/update-day-records', 'POST', $payload));
        }

        protected function postBulkUpdate(array $payload): JsonResponse
        {
            return $this->callAction('bulkUpdateAttendanceRecords', Request::create('/attendance/bulk-update', 'POST', $payload));
        }

        protected function getCalendar(int $month, int $year): JsonResponse
        {
            return $this->callAction('getAttendance', Request::create("/attendance/getAttendance/{$month}/{$year}"), ['month' => $month, 'year' => $year]);
        }

        protected function getDayRecords(int $userId, string $date): JsonResponse
        {
            return $this->callAction('getDayAttendanceRecords', Request::create('/attendance/day-records', 'GET', ['user_id' => $userId, 'date' => $date]));
        }

        protected function postCheckIn(array $payload = []): JsonResponse
        {
            return $this->callAction('checkIn', Request::create('/attendance/checkin', 'POST', $payload));
        }

        protected function postCheckOut(array $payload = []): JsonResponse
        {
            return $this->callAction('checkOut', Request::create('/attendance/checkout', 'POST', $payload));
        }

        protected function postUpdateReason(array $payload): JsonResponse
        {
            return $this->callAction('updateStatus', Request::create('/attendance/update-reason', 'POST', $payload));
        }

        protected function getEmployees(): JsonResponse
        {
            return $this->callAction('getEmployees', Request::create('/get-employees'));
        }

        protected function getAttendanceStatus(): JsonResponse
        {
            return $this->callAction('getStatus', Request::create('/attendance/status'));
        }

        // --- reading the results back --------------------------------------------------------

        /** @return array<string, mixed> */
        protected function body(JsonResponse $response): array
        {
            return json_decode($response->getContent(), true, 512, JSON_THROW_ON_ERROR);
        }

        /**
         * The persisted attendance rows for one employee-day, oldest row first.
         *
         * @return list<object>
         */
        protected function persistedRows(int $userId, string $date): array
        {
            return DB::table('attendance')
                ->where('user_id', $userId)
                ->whereDate('date', $date)
                ->orderBy('id')
                ->get()
                ->all();
        }

        protected function persistedRow(int $userId, string $date): object
        {
            $rows = $this->persistedRows($userId, $date);
            $this->assertNotEmpty($rows, "expected at least one persisted attendance row for user {$userId} on {$date}");

            return $rows[0];
        }

        protected function leaveCount(int $userId): int
        {
            return DB::table('leaves')->where('user_id', $userId)->count();
        }

        /**
         * Pulls one employee's `attendance` list out of a
         * GET /attendance/getAttendance/{month}/{year} body, keyed by date, after checking that it
         * holds one entry per date, sorted by date.
         *
         * @return array<string, array<string, mixed>>
         */
        protected function calendarEntries(JsonResponse $response, int $userId): array
        {
            $body = $this->body($response);
            $this->assertSame('success', $body['status'] ?? null);

            foreach ($body['data']['users'] as $employee) {
                if ((int) $employee['user_id'] === $userId) {
                    $dates = array_column($employee['attendance'], 'date');
                    $sorted = array_values(array_unique($dates));
                    sort($sorted);
                    $this->assertSame($sorted, $dates, "user {$userId}'s calendar must hold one entry per date, sorted by date");

                    return array_combine($dates, $employee['attendance']);
                }
            }

            $this->fail("no calendar block for user {$userId} in the response");
        }

        /** @return array<string, mixed> */
        protected function calendarEntry(JsonResponse $response, int $userId, string $date): array
        {
            $entries = $this->calendarEntries($response, $userId);
            $this->assertArrayHasKey($date, $entries, "no calendar entry for user {$userId} on {$date}");

            return $entries[$date];
        }
    }
}
