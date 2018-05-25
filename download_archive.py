from download_single_item import download_image_wrapper, download_description_wrapper, download_segmentation_wrapper, \
    fetch_img_description, save_description

import argparse
import os
import requests
from os.path import join
from multiprocessing.pool import Pool, ThreadPool
from itertools import repeat
from tqdm import tqdm


def main(num_images_requested, offset, segmentation, filter, images_dir, descs_dir, seg_dir, num_processes):
    # If any of the images dir and descs dir don't exist, create them
    create_if_none(images_dir)
    create_if_none(descs_dir)

    if filter is None:
        print('Collecting the images ids')
        ids = get_images_ids(num_images=num_images_requested, offset=offset)

        num_images_found = len(ids)
        if num_images_requested is None or num_images_found == num_images_requested:
            print('Found {0} images'.format(num_images_requested))
        else:
            print('Found {0} images and not the requested {1}'.format(num_images_found, num_images_requested))

        print('Downloading descriptions')
        descriptions = download_descriptions(ids=ids, descs_dir=descs_dir, num_processes=num_processes)

    else:
        print('Collecting ids of all the images')
        ids = get_images_ids(num_images=None, offset=offset)

        print('Downloading images descriptions, while filtering only {0} images'.format(filter))
        descriptions = download_descriptions_and_filter(ids=ids, num_images_requested=num_images_requested, filter=filter,
                                                        descs_dir=descs_dir)

        num_descs_filtered = len(descriptions)
        if num_images_requested is None or num_descs_filtered == num_images_requested:
            print('Found {0} {1} images'.format(num_images_requested, filter))
        else:
            print('Found {0} {1} images and not the requested {2}'.format(num_descs_filtered, filter,
                                                                          num_images_requested))

    # By this point we've got the description of only the required images
    print('Downloading images')
    download_images(descriptions=descriptions, images_dir=images_dir, num_processes=num_processes)

    if segmentation:
        print('Downloading segmentation')
        create_if_none(seg_dir)
        download_segmentations(descriptions=descriptions, seg_dir=seg_dir, num_processes=num_processes)

    print('Finished downloading')


def create_if_none(dir_path):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def get_images_ids(num_images, offset):
    """

    :param num_images: The number of requested images to download from the archive
    If None, will download the ids all the images in the archive
    :param offset: The offset from which to start downloading the ids of the images
    """
    # Specify the url that lists the meta data about the images (id, name, etc..)
    if num_images is None:
        num_images = 0
    url = 'https://isic-archive.com/api/v1/image?limit={0}&offset={1}&sort=name&sortdir=1'.format(num_images, offset)
    # Get the images metadata
    response = requests.get(url, stream=True)
    # Parse the metadata
    meta_data = response.json()
    # Extract the ids of the images
    ids = [meta_data[index]['_id'] for index in range(len(meta_data))]
    return ids


def download_descriptions(ids: list, descs_dir: str, num_processes: int) -> list:
    """

    :param ids:
    :param descs_dir:
    :param num_processes:
    :return: List of jsons
    """
    # Split the download among multiple threads
    pool = ThreadPool(processes=num_processes)
    descriptions = list(tqdm(pool.imap(download_description_wrapper, zip(ids, repeat(descs_dir))), total=len(ids), desc='Descriptions Downloaded'))
    return descriptions


def download_descriptions_and_filter(ids: list, num_images_requested: int, filter: str, descs_dir: str) -> list:
    """

    :param ids:
    :param num_images_requested:
    :param filter:
    :param descs_dir:
    :return: List of jsons
    """
    descriptions = []

    if num_images_requested is None:
        max_num_images = len(ids)
        pbar_desc = 'Descriptions Scanned'
    else:
        max_num_images = num_images_requested
        pbar_desc = '{0}s Found'.format(filter.title())

    pbar = tqdm(total=max_num_images, desc=pbar_desc)

    for id in ids:
        description = fetch_img_description(id)
        try:
            diagnosis = description['meta']['clinical']['benign_malignant']
        except KeyError:
            # The description doesn't have the a diagnosis. Skip it.
            continue

        if diagnosis == filter:
            # Save the description
            descriptions.append(description)
            save_description(description, descs_dir)

            if num_images_requested is not None:
                pbar.update(1)

            if num_images_requested is not None and len(descriptions) == num_images_requested:
                break

        if num_images_requested is None:
            pbar.update(1)

    pbar.close()

    return descriptions


def download_images(descriptions: list, images_dir: str, num_processes: int):
    # Split the download among multiple processes
    pool = Pool(processes=num_processes)
    list(tqdm(pool.imap(download_image_wrapper, zip(descriptions, repeat(images_dir))), total=len(descriptions), desc='Images Downloaded'))


def download_segmentations(descriptions, seg_dir, num_processes):
    # Split the download among multiple processes
    pool = Pool(processes=num_processes)
    list(tqdm(pool.imap(download_segmentation_wrapper, zip(descriptions, repeat(seg_dir))), total=len(descriptions),
         desc='Segmentations Downloaded'))


def confirm_arguments(args):
    print('You have decided to do the following:')
    if args.num_images is None:
        print('Download all the available images')
    else:
        print('Download maximum of {0} images'.format(args.num_images))

    if args.segmentation:
        print('Download segmentations as well')

    print('start with offset {0}'.format(args.offset))

    if args.filter:
        print('filter only {0} images'.format(args.filter))
    else:
        print('Use no filter (only benign / only malignant)'.format(args.filter))

    print('Images will be downloaded to ' + os.path.realpath(args.images_dir))
    print('Descriptions will be downloaded to ' + os.path.realpath(args.descs_dir))
    if args.segmentation:
        print('Segmentations will be downloaded to ' + os.path.realpath(args.seg_dir))

    print('Use {0} processes to download the archive'.format(args.p))

    res = input('Do you confirm your choices? [Y/n] ')

    while res not in ['y', '', 'n']:
        res = input('Invalid input. Do you confirm your choices? [Y/n] ')
    if res in ['y', '']:
        return True
    if res == 'n':
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--num_images', type=int, help='The number of images you would like to download from the ISIC Archive. '
                                                        'Leave empty to download all the available images', default=None)
    parser.add_argument('--offset', type=int, help='The offset of the image index from which to start downloading', default=0)
    parser.add_argument('-s', '--segmentation', help='Whether to download the segmentation of the images as well', action="store_true")
    parser.add_argument('--filter', help='Indicates whether to download only benign or malignant images', choices=['benign', 'malignant'], default=None)
    parser.add_argument('--images-dir', help='The directory in which the images will be downloaded to',
                        default=join('Data', 'Images'))
    parser.add_argument('--descs-dir', help='The directory in which the descriptions of '
                                            'the images will be downloaded to',
                        default=join('Data', 'Descriptions'))
    parser.add_argument('--seg-dir', help='The directory in which the segmentation of '
                                            'the images will be downloaded to',
                        default=join('Data', 'Segmentation'))
    parser.add_argument('--p', type=int, help='The number of processes to use in parallel', default=16)
    args = parser.parse_args()

    has_confirmed = confirm_arguments(args)

    if has_confirmed:
        main(num_images_requested=args.num_images, offset=args.offset, segmentation=args.segmentation,
             filter=args.filter, images_dir=args.images_dir, descs_dir=args.descs_dir, seg_dir=args.seg_dir,
             num_processes=args.p)
    else:
        print('Exiting without downloading anything')