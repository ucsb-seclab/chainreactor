(define (problem download-file)
  (:domain micronix)
  (:objects
    downloader reader writer - executable
    file - file
    data - data
    user - user
    group - group
    process - process
    remote - remote
    local - local
  )

  (:init
    (CAP_read_file reader)
    (CAP_write_file writer)
    (CAP_download_file downloader)
    (system_executable reader)
    (system_executable writer)
    (system_executable downloader)
    
    (controlled_user user)
    (user_group user group)
    
    (file_present_at_location file remote)
  )

  (:goal (and
      (file_present_at_location file local)
    )
  )
)