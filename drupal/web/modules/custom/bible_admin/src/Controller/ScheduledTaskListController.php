<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Controller;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\Request;

/**
 * The scheduled tasks of the tasks this user may see: the coming ones by date, and the past ones (latest first)
 * folded away below, each with Edit and Remove. Also the Scheduled task report (report()), to print.
 */
class ScheduledTaskListController extends ControllerBase {

  public function __construct(private readonly BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function build(): array {
    $build = [
      '#cache' => ['max-age' => 0],
      'intro' => [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Who does which task on which date. To schedule one, use Schedule beside the task on the <a href=":tasks">Tasks</a> page and choose the site user and one of its next four dates. Schedule tasks fills a whole day at once, and the Scheduled Task Report lists them day by day, ready to print.', [
          ':tasks' => Url::fromRoute('bible_admin.tasks')->toString(),
        ]),
      ],
    ];
    try {
      $schedules = $this->manager->listScheduledTasks();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $showOwner = $this->currentUser()->hasPermission('administer signatures and tasks');
    $coming = array_values(array_filter($schedules, fn ($schedule) => !$schedule['past']));
    $past = array_reverse(array_values(array_filter($schedules, fn ($schedule) => $schedule['past'])));

    $build['#attached']['library'][] = 'bible_admin/sortable_table';
    $build['coming'] = $this->table($coming, $showOwner, $this->t('Nothing is scheduled from today on.'), 'ascending');
    if ($past) {
      $build['past'] = [
        '#type' => 'details',
        '#title' => $this->t('Past (@count)', ['@count' => count($past)]),
        '#open' => FALSE,
        'table' => $this->table($past, $showOwner, '', 'descending'),
      ];
    }
    return $build;
  }

  /**
   * The Scheduled task report (added 2026-11-23 at the owner's request, like their paper sign-up sheet): the
   * scheduled tasks from one date to another (today and four weeks on, to start), a section for each day with a
   * row per task: the task, the person, the note, their email and their phone. Only days with something
   * scheduled appear. Print prints only the report (css/scheduled-task-report.css).
   */
  public function report(Request $request): array {
    // Today in this user's time zone, as a plain date like the ones typed in the boxes.
    $zone = new \DateTimeZone($this->currentUser()->getTimeZone() ?: 'UTC');
    $today = $this->dateFrom((new \DateTimeImmutable('now', $zone))->format('Y-m-d'));
    $from = $this->dateFrom((string) $request->query->get('from', '')) ?? $today;
    $to = $this->dateFrom((string) $request->query->get('to', '')) ?? $from->modify('+27 days');
    if ($to->format('Y-m-d') < $from->format('Y-m-d')) {
      [$from, $to] = [$to, $from];
    }
    $build = [
      '#cache' => ['max-age' => 0],
      '#attached' => ['library' => ['bible_admin/scheduled_task_report']],
      'filters' => [
        '#type' => 'inline_template',
        '#template' => '<form method="get" class="scheduled-task-report-filters">'
          . '<label>{{ from_label }}<input type="date" name="from" value="{{ from }}"></label>'
          . '<label>{{ to_label }}<input type="date" name="to" value="{{ to }}"></label>'
          . '<button type="submit" class="button">{{ show }}</button>'
          . '<button type="button" class="button button--primary" data-print-report>{{ print }}</button>'
          . '<a href="{{ back_url }}">{{ back }}</a>'
          . '</form>',
        '#context' => [
          'from_label' => $this->t('From'),
          'to_label' => $this->t('To'),
          'from' => $from->format('Y-m-d'),
          'to' => $to->format('Y-m-d'),
          'show' => $this->t('Show'),
          'print' => $this->t('Print'),
          'back' => $this->t('Back to the scheduled tasks'),
          'back_url' => Url::fromRoute('bible_admin.scheduled_tasks')->toString(),
        ],
      ],
      'report' => [
        '#type' => 'container',
        '#attributes' => ['class' => ['scheduled-task-report']],
        // Shown only when printing, since the page's own title is not printed.
        'title' => ['#type' => 'html_tag', '#tag' => 'h1', '#value' => $this->t('Scheduled Task Report'), '#attributes' => ['class' => ['scheduled-task-report-title']]],
      ],
    ];
    try {
      $schedules = $this->manager->listScheduledTasks();
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      return $build;
    }
    $days = [];
    foreach ($schedules as $schedule) {
      if ($schedule['on_date'] >= $from->format('Y-m-d') && $schedule['on_date'] <= $to->format('Y-m-d')) {
        $days[$schedule['on_date']][] = $schedule;
      }
    }
    ksort($days);
    if (!$days) {
      $build['report']['empty'] = [
        '#type' => 'html_tag',
        '#tag' => 'p',
        '#value' => $this->t('Nothing is scheduled from @from to @to.', ['@from' => $this->longDay($from->format('Y-m-d')), '@to' => $this->longDay($to->format('Y-m-d'))]),
      ];
      return $build;
    }
    foreach ($days as $day => $daySchedules) {
      usort($daySchedules, fn ($first, $second) => [mb_strtolower($first['task_name']), mb_strtolower($first['user_name'])] <=> [mb_strtolower($second['task_name']), mb_strtolower($second['user_name'])]);
      $rows = [];
      foreach ($daySchedules as $schedule) {
        $rows[] = [
          ['data' => ['#plain_text' => $schedule['task_name']]],
          ['data' => ['#plain_text' => $schedule['user_name'] !== '' ? $schedule['user_name'] : $schedule['user_label']]],
          ['data' => ['#plain_text' => $schedule['note_text']], 'class' => ['scheduled-task-report-notes']],
          ['data' => ['#plain_text' => $schedule['email']]],
          ['data' => ['#plain_text' => $schedule['phone']]],
          ['data' => ['#plain_text' => !empty($schedule['confirmed']) ? (string) $this->t('Yes') : (string) $this->t('No')]],
        ];
      }
      $build['report']['day_' . $day] = [
        '#type' => 'container',
        '#attributes' => ['class' => ['scheduled-task-report-day']],
        'heading' => ['#type' => 'html_tag', '#tag' => 'h2', '#value' => $this->longDay($day)],
        'table' => [
          '#type' => 'table',
          '#header' => [$this->t('Task'), $this->t('Name'), $this->t('Notes'), $this->t('Email'), $this->t('Phone (Text)'), $this->t('Confirmed')],
          '#colgroups' => [[['class' => ['task']], ['class' => ['name']], ['class' => ['notes']], ['class' => ['email']], ['class' => ['phone']], ['class' => ['confirmed']]]],
          '#rows' => $rows,
        ],
      ];
    }
    return $build;
  }

  /**
   * A date typed in the report's From or To box (Y-m-d), or NULL when there is none or it is not a date.
   */
  private function dateFrom(string $value): ?\DateTimeImmutable {
    $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $value, new \DateTimeZone('UTC'));
    return $date !== FALSE && $date->format('Y-m-d') === $value ? $date : NULL;
  }

  /**
   * A day such as "Sunday, December 6, 2026" (a date with no time, so no time zone change).
   */
  private function longDay(string $day): string {
    $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $day, new \DateTimeZone('UTC'));
    return $date === FALSE ? $day : $date->format('l, F j, Y');
  }

  /**
   * One table of scheduled tasks. Date, Task and Site user sort by a click on their header (2026-11-23, the owner's
   * request; js/sortable-table.js); the rows come sorted by date ($dateOrder: the coming ones soonest first, the
   * past ones latest first), and the Date header says so.
   */
  private function table(array $schedules, bool $showOwner, $empty, string $dateOrder): array {
    $rows = [];
    foreach ($schedules as $schedule) {
      $links = [
        ['title' => $this->t('Edit'), 'url' => Url::fromRoute('bible_admin.scheduled_task_edit', ['schedule_id' => $schedule['id']])],
        ['title' => $this->t('Remove'), 'url' => Url::fromRoute('bible_admin.scheduled_task_remove', ['schedule_id' => $schedule['id']])],
      ];
      $row = [
        ['data' => ['#plain_text' => $this->formatDay($schedule['on_date'])], 'data-sort-value' => $schedule['on_date']],
        ['data' => ['#plain_text' => $schedule['task_name']]],
        ['data' => ['#plain_text' => $schedule['user_label']]],
        ['data' => ['#plain_text' => !empty($schedule['confirmed']) ? (string) $this->t('Yes') : (string) $this->t('No')]],
        ['data' => $this->reminders($schedule)],
      ];
      if ($showOwner) {
        $row[] = ['data' => ['#plain_text' => $schedule['owner_name']]];
      }
      $row[] = ['data' => ['#plain_text' => $schedule['created_by_name']]];
      $row[] = ['data' => ['#type' => 'operations', '#links' => $links]];
      $rows[] = $row;
    }
    $header = [
      ['data' => $this->t('Date'), 'data-sort-default' => $dateOrder],
      $this->t('Task'),
      $this->t('Site user'),
      $this->t('Confirmed'),
      ['data' => $this->t('Reminders'), 'data-no-sort' => ''],
    ];
    if ($showOwner) {
      $header[] = ['data' => $this->t('Task owner'), 'data-no-sort' => ''];
    }
    $header[] = ['data' => $this->t('Scheduled by'), 'data-no-sort' => ''];
    $header[] = ['data' => $this->t('Operations'), 'data-no-sort' => ''];
    return [
      '#type' => 'table',
      '#header' => $header,
      '#rows' => $rows,
      '#empty' => $empty,
      '#attributes' => ['class' => ['bible-admin-sortable']],
    ];
  }

  /**
   * Each reminder the task sends: its day, and how it went (or nothing yet). "None" when the task sends none.
   */
  private function reminders(array $schedule): array {
    $items = [];
    foreach (['first' => $this->t('First'), 'second' => $this->t('Second')] as $which => $label) {
      if ($schedule[$which . '_notice_date'] === NULL) {
        continue;
      }
      $outcome = $schedule[$which . '_notice_result'] !== '' ? $schedule[$which . '_notice_result'] : $this->t('not sent yet');
      $items[] = $this->t('@which, @day: @outcome', [
        '@which' => $label,
        '@day' => $this->formatDay($schedule[$which . '_notice_date']),
        '@outcome' => $outcome,
      ]);
    }
    return $items ? ['#theme' => 'item_list', '#items' => $items] : ['#plain_text' => (string) $this->t('None')];
  }

  /**
   * A day such as "Sun, Nov 22, 2026" (a date with no time, so no time zone change).
   */
  private function formatDay(string $day): string {
    $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $day, new \DateTimeZone('UTC'));
    return $date === FALSE ? $day : $date->format('D, M j, Y');
  }

}
