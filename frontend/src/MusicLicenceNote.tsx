// The licence notice of the Christian music section, at the foot of the music page and in the Help page's
// music section. The wording is the site owner's (2026-11-10).
const LICENCE_ADDRESS = 'https://creativecommons.org/licenses/by-nc-sa/4.0/'

function MusicLicenceNote() {
  return (
    <>
      Some songs are licensed under a{' '}
      <a href={LICENCE_ADDRESS} target="_blank" rel="noopener noreferrer license">
        Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License
      </a>
      .
    </>
  )
}

export default MusicLicenceNote
