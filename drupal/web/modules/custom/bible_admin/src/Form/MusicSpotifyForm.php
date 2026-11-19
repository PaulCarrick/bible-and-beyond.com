<?php

declare(strict_types=1);

namespace Drupal\bible_admin\Form;

use Drupal\bible_admin\BibleManager;
use Drupal\bible_admin\BibleManagerException;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Adds or changes a Spotify item in the Christian music (the owner's request, 2026-11-19): a Spotify link to a song,
 * album, playlist, podcast episode or show, or artist, in place of a file, with a title, author, keywords and words
 * like a song. The site shows Spotify's own embedded player for it. Like a song, a new one is hidden until published.
 */
class MusicSpotifyForm extends FormBase {

  public function __construct(protected BibleManager $manager) {}

  public static function create(ContainerInterface $container): static {
    return new static($container->get('bible_admin.manager'));
  }

  public function getFormId(): string {
    return 'bible_admin_music_spotify';
  }

  public function buildForm(array $form, FormStateInterface $form_state, ?string $song_id = NULL): array {
    $form['#cache'] = ['max-age' => 0];
    $song = NULL;
    if ($song_id !== NULL) {
      try {
        $song = $this->manager->getMusic($song_id);
      }
      catch (BibleManagerException $exception) {
        $this->messenger()->addError($exception->getMessage());
        return ['back' => ['#type' => 'link', '#title' => $this->t('Back to the Christian music'), '#url' => Url::fromRoute('bible_admin.music')]];
      }
      if ($song['kind'] !== 'spotify') {
        $this->messenger()->addError($this->t('That is a song with a file: edit it on its own form.'));
        return ['back' => ['#type' => 'link', '#title' => $this->t('Edit the song'), '#url' => Url::fromRoute('bible_admin.music_edit', ['song_id' => $song['id']])]];
      }
      $form_state->set('song_id', $song['id']);
    }
    $form['intro'] = [
      '#type' => 'html_tag',
      '#tag' => 'p',
      '#value' => $this->t('A song, album or playlist on Spotify, shown on the site with Spotify\'s own player: visitors signed in to Spotify in their browser hear it in full, others hear 30-second previews. Like a song, it is hidden until you publish it. It cannot go in a visitor\'s playlist.'),
    ];
    if ($song === NULL) {
      $form['id'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Id'),
        '#description' => $this->t('3 to 50 lowercase letters, digits and hyphens, such as worship-playlist. It names the item in the site\'s addresses.'),
        '#required' => TRUE,
        '#maxlength' => 50,
        '#size' => 30,
      ];
    }
    $form['spotify_link'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Spotify link'),
      '#default_value' => $song !== NULL ? 'https://open.spotify.com/' . $song['spotify_link'] : '',
      '#required' => TRUE,
      '#maxlength' => 500,
      '#placeholder' => 'https://open.spotify.com/playlist/…',
      '#description' => $this->t('In Spotify, open the song, album or playlist, then Share, Copy link, and paste it here.'),
    ];
    $form['title'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Title'),
      '#default_value' => $song['title'] ?? '',
      '#required' => TRUE,
      '#maxlength' => 200,
    ];
    $form['author'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Author'),
      '#description' => $this->t('Who sings or plays it, or whose playlist it is. Optional.'),
      '#default_value' => $song['author'] ?? '',
      '#maxlength' => 200,
    ];
    $form['keywords'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Keywords'),
      '#description' => $this->t('Words or phrases, separated by commas, that a visitor might search for, for example "worship, hymns, Easter". Search the media finds it by them, its title, author and words: the site cannot search inside Spotify. Optional.'),
      '#default_value' => $song['keywords'] ?? '',
      '#maxlength' => 500,
    ];
    $form['lyrics'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Words or description'),
      '#description' => $this->t('Shown under the player, line by line as typed. Optional.'),
      '#default_value' => $song['lyrics'] ?? '',
      '#rows' => 8,
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = ['#type' => 'submit', '#value' => $song === NULL ? $this->t('Add the Spotify item') : $this->t('Save')];
    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('bible_admin.music'),
      '#attributes' => ['class' => ['button']],
    ];
    return $form;
  }

  public function submitForm(array &$form, FormStateInterface $form_state): void {
    $songId = $form_state->get('song_id');
    $details = [
      'spotify_link' => trim((string) $form_state->getValue('spotify_link')),
      'title' => (string) $form_state->getValue('title'),
      'author' => (string) $form_state->getValue('author'),
      'keywords' => (string) $form_state->getValue('keywords'),
      'lyrics' => (string) $form_state->getValue('lyrics'),
    ];
    try {
      $song = $this->manager->saveSpotifyMusic($songId ?? strtolower(trim((string) $form_state->getValue('id'))), $details, $songId === NULL);
    }
    catch (BibleManagerException $exception) {
      $this->messenger()->addError($exception->getMessage());
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($songId === NULL
      ? $this->t('Added “@title”. It is hidden until you publish it.', ['@title' => $song['title']])
      : $this->t('Saved “@title”.', ['@title' => $song['title']]));
    $form_state->setRedirect('bible_admin.music');
  }

}
