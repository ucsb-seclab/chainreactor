(define (problem upload-file)
  (:domain micronix)
  (:objects
    uploader reader writer - executable
    file - file
    data - data
    user - user
    group - group
    process - process
    local - local
    remote - remote
  )

  (:init
    (CAP_read_file reader)
    (CAP_write_file writer)
    (CAP_upload_file uploader)
    (system_executable reader)
    (system_executable writer)
    (system_executable uploader)
    
    (controlled_user user)
    (user_group user group)
    (file_owner file user group)
    (file_present_at_location file local)
  )

  (:goal (and
      (file_present_at_location file remote)
    )
  )
)