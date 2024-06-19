(define (problem add-permission)
  (:domain micronix)
  (:objects
    alice - user
    directory - directory
    chmod - executable
    process - process
    data - data
    group - group
  )

  (:init
    (CAP_change_permission chmod)
    (system_executable chmod)

    (directory_owner directory alice group)
    (user_group alice group)
    (controlled_user alice)
  )

  (:goal (default_directory_permission directory FS_WRITE))
)